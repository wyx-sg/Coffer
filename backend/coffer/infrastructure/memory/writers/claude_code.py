"""Writes hub entries into Claude Code's own memory (spec memory "Write the hub
into Claude Code's native memory", "Write global memories into a Claude Code
rules file").

- **Project memories** go to ``<config_dir>/projects/<slug>/memory/``, the
  directory Claude Code itself keeps for a repository root (``slug`` is
  :func:`coffer.domain.agent.native_memory.encode_slug` of the root, shared by
  every worktree of it), as one topic file per memory, ``coffer_<slug>.md``,
  in Claude Code's own frontmatter (``name``, ``description``,
  ``metadata.type``) plus a ``coffer:`` block naming the hub entry.
- **The index**: one line per copy inside a marked block at the end of that
  directory's ``MEMORY.md``, newest first, at most :data:`BLOCK_CAP` lines and
  then one line naming the rest. Only the bytes between the markers change;
  the file is backed up before each change.
- **Global memories** go to ``<config_dir>/rules/coffer-memory.md``, a file
  Coffer owns, which Claude Code loads in every session.
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping, Sequence
from typing import Any

from coffer.domain.agent.native_memory import encode_slug
from coffer.domain.memory.hub import AGENT_LABELS, check_segment, one_line, title_slug
from coffer.domain.memory.native_writer import (
    STATUS_MISSING,
    STATUS_OK,
    AuxWrite,
    WriterStatus,
)
from coffer.domain.memory.sync_plan import STATE_WRITTEN, CopyRecord, Target
from coffer.infrastructure.memory import native_files
from coffer.infrastructure.memory.frontmatter import render_frontmatter

#: Every copy's file name starts with this.
COPY_PREFIX = "coffer_"
INDEX_NAME = "MEMORY.md"
RULES_NAME = "coffer-memory.md"
BLOCK_BEGIN = "<!-- coffer:memory-sync:begin -->"
BLOCK_END = "<!-- coffer:memory-sync:end -->"
#: Lines the block lists before naming the rest (of Claude Code's 200).
BLOCK_CAP = 30
#: The rules file's size bound; the newest memories first.
RULES_MAX_BYTES = 25 * 1024

RULES_HEADER = (
    "# Memories from your other agents\n\n"
    "Coffer writes this file from what your other coding agents learned about you "
    "on your machines. Do not edit it: change the memory in the agent that wrote "
    "it, and Coffer brings the change here.\n"
)


def is_coffer_copy(name: str, frontmatter: Mapping[str, Any]) -> bool:
    """Whether a memory file is a copy Coffer wrote: its name starts with
    ``coffer_`` **and** its frontmatter names a hub entry."""
    coffer = frontmatter.get("coffer")
    return name.startswith(COPY_PREFIX) and isinstance(coffer, dict) and bool(coffer.get("entry"))


def memory_dir(config_dir: str, root: str) -> pathlib.Path:
    """Claude Code's memory directory for the repository at ``root``."""
    slug = check_segment(encode_slug(root.rstrip("/")))
    return pathlib.Path(config_dir) / "projects" / slug / "memory"


def rules_path(config_dir: str) -> pathlib.Path:
    return pathlib.Path(config_dir) / "rules" / RULES_NAME


def replace_block(text: str, lines: Sequence[str]) -> str:
    """``text`` with Coffer's block holding ``lines``: replaced between the
    markers when they are there, appended otherwise, removed when ``lines`` is
    empty. Nothing outside the markers changes."""
    begin, end = text.find(BLOCK_BEGIN), text.find(BLOCK_END)
    block = "\n".join([BLOCK_BEGIN, *lines, BLOCK_END]) if lines else ""
    if begin != -1 and end > begin:
        tail = text[end + len(BLOCK_END) :]
        head = text[:begin]
        if not block:
            # Drop the separator newline Coffer added when it appended the block.
            if head.endswith("\n\n"):
                head = head[:-1]
            if tail.startswith("\n"):
                tail = tail[1:]
            return head + tail
        return head + block + tail
    if not block:
        return text
    if not text:
        return block + "\n"
    return text + ("\n" if text.endswith("\n") else "\n\n") + block + "\n"


class ClaudeCodeMemoryWriter:
    """``NativeWriter`` for Claude Code."""

    agent_type = "claude_code"

    def status(self, config_dir: str) -> WriterStatus:
        if not pathlib.Path(config_dir).is_dir():
            return WriterStatus(STATUS_MISSING, config_dir, "the config directory is not there")
        return WriterStatus(STATUS_OK, config_dir)

    def wants(self, target: Target) -> bool:
        return target.root is not None

    def path_for(self, config_dir: str, target: Target, taken: set[str]) -> str:
        assert target.root is not None
        folder = memory_dir(config_dir, target.root)
        slug = title_slug(target.entry.title)
        for name in (
            f"{COPY_PREFIX}{slug}.md",
            f"{COPY_PREFIX}{slug}-{target.entry.id[:6]}.md",
        ):
            path = str(folder / name)
            if path not in taken and not pathlib.Path(path).exists():
                return path
        n = 2
        while True:
            path = str(folder / f"{COPY_PREFIX}{slug}-{target.entry.id[:6]}-{n}.md")
            if path not in taken and not pathlib.Path(path).exists():
                return path
            n += 1

    def render(self, target: Target) -> str:
        entry = target.entry
        origin = AGENT_LABELS.get(entry.origin.agent, entry.origin.agent)
        fm: dict[str, Any] = {
            "name": entry.title,
            "description": one_line(entry.description or entry.title),
            "metadata": {"type": entry.type},
            "coffer": {
                "entry": entry.id,
                "from": entry.origin.agent,
                "synced_at": entry.updated_at,
            },
        }
        body = target.body.strip("\n")
        return render_frontmatter(fm, f"\n{body}\n\n_Learned by {origin}; synced by Coffer._\n")

    def aux(
        self,
        config_dir: str,
        copies: Mapping[str, CopyRecord],
        targets: Mapping[str, Target],
        global_targets: Sequence[Target],
    ) -> list[AuxWrite]:
        out: list[AuxWrite] = []
        # Every folder holding a block, so one whose last copy went is emptied.
        by_dir: dict[pathlib.Path, list[tuple[str, CopyRecord]]] = {
            folder: [] for folder in _block_folders(config_dir)
        }
        for path, rec in copies.items():
            by_dir.setdefault(pathlib.Path(path).parent, [])
            if rec.state == STATE_WRITTEN and rec.entry in targets:
                by_dir[pathlib.Path(path).parent].append((path, rec))
        for folder, live in sorted(by_dir.items()):
            index = folder / INDEX_NAME
            current = native_files.read(index) or ""
            lines = _index_lines(live, targets)
            new = replace_block(current, lines)
            if new != current:
                out.append(AuxWrite(str(index), new or None, backup=bool(current)))
        rules = rules_path(config_dir)
        if global_targets:
            out.append(AuxWrite(str(rules), _render_rules(global_targets)))
        elif rules.exists():
            out.append(AuxWrite(str(rules), None))
        return out

    def undo(self, config_dir: str, copies: Mapping[str, CopyRecord]) -> list[AuxWrite]:
        out: list[AuxWrite] = []
        folders = {pathlib.Path(p).parent for p in copies} | set(_block_folders(config_dir))
        for folder in sorted(folders):
            index = folder / INDEX_NAME
            current = native_files.read(index)
            if current is None or BLOCK_BEGIN not in current:
                continue
            new = replace_block(current, [])
            out.append(AuxWrite(str(index), new or None, backup=True))
        rules = rules_path(config_dir)
        if rules.exists():
            out.append(AuxWrite(str(rules), None))
        return out


def _block_folders(config_dir: str) -> list[pathlib.Path]:
    """Every project memory folder whose ``MEMORY.md`` holds Coffer's block."""
    projects = pathlib.Path(config_dir) / "projects"
    try:
        dirs = [d / "memory" for d in projects.iterdir() if d.is_dir()]
    except OSError:
        return []
    return [d for d in dirs if BLOCK_BEGIN in (native_files.read(d / INDEX_NAME) or "")]


def _index_lines(
    live: Sequence[tuple[str, CopyRecord]], targets: Mapping[str, Target]
) -> list[str]:
    rows = sorted(
        ((targets[rec.entry], pathlib.Path(path).name) for path, rec in live),
        key=lambda row: (row[0].entry.updated_at, row[1]),
        reverse=True,
    )
    lines = []
    for target, name in rows[:BLOCK_CAP]:
        entry = target.entry
        origin = AGENT_LABELS.get(entry.origin.agent, entry.origin.agent)
        desc = one_line(entry.description or entry.title, 150)
        lines.append(f"- [{one_line(entry.title, 80)}]({name}) — {desc} (from {origin})")
    rest = len(rows) - BLOCK_CAP
    if rest > 0:
        lines.append(f"- …and {rest} more Coffer memories in this folder ({COPY_PREFIX}*.md)")
    return lines


def _render_rules(targets: Sequence[Target]) -> str:
    ordered = sorted(targets, key=lambda t: (t.entry.updated_at, t.entry.id), reverse=True)
    parts = [RULES_HEADER]
    size = len(RULES_HEADER.encode("utf-8"))
    written = 0
    for target in ordered:
        entry = target.entry
        origin = AGENT_LABELS.get(entry.origin.agent, entry.origin.agent)
        section = (
            f"\n## {one_line(entry.title, 120)}\n\n"
            f"{one_line(entry.description, 300)}\n\n"
            f"{target.body.strip()}\n\n_Learned by {origin}._\n"
        )
        if size + len(section.encode("utf-8")) > RULES_MAX_BYTES:
            break
        parts.append(section)
        size += len(section.encode("utf-8"))
        written += 1
    rest = len(ordered) - written
    if rest > 0:
        parts.append(f"\n_{rest} older memories are not listed here to keep this file short._\n")
    return "".join(parts)


__all__ = [
    "BLOCK_BEGIN",
    "BLOCK_CAP",
    "BLOCK_END",
    "COPY_PREFIX",
    "RULES_NAME",
    "ClaudeCodeMemoryWriter",
    "is_coffer_copy",
    "memory_dir",
    "replace_block",
    "rules_path",
]
