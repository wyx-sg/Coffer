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
- **Global memories** are written the same way into a project folder of their
  own, :data:`GLOBAL_ROOT`'s, which no session opens by itself; so
  ``<config_dir>/rules/coffer-memory.md``, a file Coffer owns that Claude Code
  loads in every session, says where they are. It lists the standing memories
  (about the person, or how they work) one short line each, and names the task
  groups the rest were learned in; that folder's ``MEMORY.md`` block lists every
  memory under its group, uncapped, for a session to read when a topic matches.
  The rules file never holds their text.
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
from coffer.infrastructure.memory.writers.claude_code_lines import (
    BLOCK_CAP,
    COPY_PREFIX,
    INDEX_NAME,
    global_index_lines,
    index_lines,
    render_rules,
)

RULES_NAME = "coffer-memory.md"
BLOCK_BEGIN = "<!-- coffer:memory-sync:begin -->"
BLOCK_END = "<!-- coffer:memory-sync:end -->"
#: The pseudo project global memories are filed under: Claude Code names a
#: project's memory folder after its root, and no session runs here.
GLOBAL_ROOT = "/coffer-global"


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
        return True

    def path_for(self, config_dir: str, target: Target, taken: set[str]) -> str:
        folder = memory_dir(config_dir, target.root or GLOBAL_ROOT)
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
        global_folder = memory_dir(config_dir, GLOBAL_ROOT)
        for folder, live in sorted(by_dir.items()):
            index = folder / INDEX_NAME
            current = native_files.read(index) or ""
            if folder == global_folder:
                lines = global_index_lines(live, targets)
            else:
                lines = index_lines(live, targets)
            new = replace_block(current, lines)
            if new != current:
                out.append(AuxWrite(str(index), new or None, backup=bool(current)))
        rules = rules_path(config_dir)
        live_global = by_dir.get(global_folder, [])
        if live_global:
            out.append(AuxWrite(str(rules), render_rules(global_folder, live_global, targets)))
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
