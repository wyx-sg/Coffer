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
from coffer.domain.memory.hub import (
    AGENT_LABELS,
    CODEX,
    HubEntry,
    check_segment,
    one_line,
    title_slug,
)
from coffer.domain.memory.native_writer import (
    STATUS_MISSING,
    STATUS_OK,
    AuxWrite,
    WriterStatus,
)
from coffer.domain.memory.sync_plan import STATE_WRITTEN, CopyRecord, Target
from coffer.infrastructure.memory import native_files
from coffer.infrastructure.memory.codex_identity import is_profile, task_group
from coffer.infrastructure.memory.frontmatter import render_frontmatter

#: Every copy's file name starts with this.
COPY_PREFIX = "coffer_"
INDEX_NAME = "MEMORY.md"
RULES_NAME = "coffer-memory.md"
BLOCK_BEGIN = "<!-- coffer:memory-sync:begin -->"
BLOCK_END = "<!-- coffer:memory-sync:end -->"
#: Lines the block lists before naming the rest (of Claude Code's 200).
BLOCK_CAP = 30
#: The pseudo project global memories are filed under: Claude Code names a
#: project's memory folder after its root, and no session runs here.
GLOBAL_ROOT = "/coffer-global"
#: The rules file's size bound. Every session loads it, so it stays near 2k
#: tokens; what does not fit is still in the global folder's ``MEMORY.md``.
RULES_MAX_BYTES = 8 * 1024
#: Characters of title and description a standing memory's line shows.
RULES_LINE_TEXT = 120
#: The bound on the line naming the task groups.
RULES_TOPICS_MAX_BYTES = 2 * 1024

#: The heading over the memories that apply whatever the task.
STANDING_HEADING = "About the person and how they work"

RULES_HEADER = (
    "# Memories from your other agents\n\n"
    "Coffer writes this file. Do not edit it: change the memory in the agent that "
    "wrote it, and Coffer brings the change here.\n"
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
                lines = _global_index_lines(live, targets)
            else:
                lines = _index_lines(live, targets)
            new = replace_block(current, lines)
            if new != current:
                out.append(AuxWrite(str(index), new or None, backup=bool(current)))
        rules = rules_path(config_dir)
        live_global = by_dir.get(global_folder, [])
        if live_global:
            out.append(AuxWrite(str(rules), _render_rules(global_folder, live_global, targets)))
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


def _newest_first(
    live: Sequence[tuple[str, CopyRecord]], targets: Mapping[str, Target]
) -> list[tuple[Target, str]]:
    """Each live copy's target and file name, the newest memory first."""
    return sorted(
        ((targets[rec.entry], pathlib.Path(path).name) for path, rec in live),
        key=lambda row: (row[0].entry.updated_at, row[1]),
        reverse=True,
    )


def _index_line(target: Target, name: str) -> str:
    entry = target.entry
    origin = AGENT_LABELS.get(entry.origin.agent, entry.origin.agent)
    title, gloss = _title_and_rest(entry.title, entry.description, 150)
    link = f"[{one_line(title, 80)}]({name})" if title else f"[{gloss}]({name})"
    gloss = gloss.lstrip(_SEPARATORS) if title else ""
    tail = f" — {gloss}" if gloss else ""
    return f"- {link}{tail} (from {origin})"


def _index_lines(
    live: Sequence[tuple[str, CopyRecord]], targets: Mapping[str, Target]
) -> list[str]:
    rows = _newest_first(live, targets)
    lines = [_index_line(target, name) for target, name in rows[:BLOCK_CAP]]
    rest = len(rows) - BLOCK_CAP
    if rest > 0:
        lines.append(f"- …and {rest} more Coffer memories in this folder ({COPY_PREFIX}*.md)")
    return lines


def _group_of(entry: HubEntry) -> str:
    """The task group a memory was learned in, or ``""`` for a standing one."""
    return task_group(entry.origin.source) if entry.origin.agent == CODEX else ""


def _split_global(
    rows: Sequence[tuple[Target, str]],
) -> tuple[list[tuple[Target, str]], dict[str, list[tuple[Target, str]]]]:
    """The standing memories (the profile first) and the rest by task group,
    each group in the order its newest memory comes."""
    standing: list[tuple[Target, str]] = []
    groups: dict[str, list[tuple[Target, str]]] = {}
    for row in rows:
        group = _group_of(row[0].entry)
        if group:
            groups.setdefault(group, []).append(row)
        else:
            standing.append(row)
    standing.sort(key=lambda row: not _pinned(row[0].entry))
    return standing, groups


def _pinned(entry: HubEntry) -> bool:
    return entry.origin.agent == CODEX and is_profile(entry.origin.source)


def _global_index_lines(
    live: Sequence[tuple[str, CopyRecord]], targets: Mapping[str, Target]
) -> list[str]:
    """The global folder's block: every memory, the standing ones first, then
    each task group under its name. No session loads this file by itself, so it
    is not capped; the rules file points at it."""
    standing, groups = _split_global(_newest_first(live, targets))
    lines: list[str] = []
    if standing:
        lines += [f"## {STANDING_HEADING}", *(_index_line(t, n) for t, n in standing)]
    for group, rows in groups.items():
        lines += [f"## {one_line(group, 120)}", *(_index_line(t, n) for t, n in rows)]
    return lines


#: What a title's remainder can open with to follow the title directly.
_JOINERS = (";", ",", ".", ":", " ")
#: Separators trimmed off a remainder that is shown on its own.
_SEPARATORS = " ;,.:->"


def _title_and_rest(title: str, description: str, limit: int) -> tuple[str, str]:
    """``title`` and what ``description`` adds to it, each on one line.

    A Codex memory has no title of its own: its title is the first clause of its
    text, and its description is the whole text, so printing both repeats that
    clause. When the description begins with the title, only the remainder is
    returned (``""`` when there is none); when the title is a cut-off stem of the
    description, the title is dropped (``""``) and the description returned."""
    t, d = one_line(title, 10_000), one_line(description, 10_000)
    if not d or d == t:
        return t, ""
    if d.startswith(t):
        rest = d[len(t) :]
        if not rest.strip():
            return t, ""
        # Keep the separator that joined the clause to the rest ("; ", " -> ").
        return t, (" " if rest[0] == " " else "") + one_line(rest, limit)
    for ellipsis in ("...", "…"):
        stem = t[: -len(ellipsis)].rstrip() if t.endswith(ellipsis) else ""
        if stem and d.startswith(stem):
            return "", one_line(d, limit)
    return t, one_line(d, limit)


def _rules_text(entry: HubEntry) -> str:
    """A standing memory's title, and as much of what its description adds as
    fits in :data:`RULES_LINE_TEXT` characters."""
    title, gloss = _title_and_rest(entry.title, entry.description, RULES_LINE_TEXT)
    if not title:
        return gloss
    title = one_line(title, RULES_LINE_TEXT)
    room = RULES_LINE_TEXT - len(title) - 2  # the ": " a gloss may need
    if room < 40:
        return f"**{title}**"
    _, gloss = _title_and_rest(entry.title, entry.description, room)
    if not gloss:
        return f"**{title}**"
    sep = "" if gloss[:1] in _JOINERS else ": "
    return f"**{title}**{sep}{gloss}"


def _topics_line(groups: Mapping[str, Sequence[tuple[Target, str]]]) -> str:
    names = [f"{one_line(group, 60)} ({len(rows)})" for group, rows in groups.items()]
    line = ""
    for i, name in enumerate(names):
        more = f"; …and {len(names) - i} more topics" if i else ""
        candidate = f"{line}; {name}" if line else name
        if len(candidate.encode("utf-8")) + len(more.encode("utf-8")) > RULES_TOPICS_MAX_BYTES:
            return line + f"; …and {len(names) - i} more topics"
        line = candidate
    return line


def _render_rules(
    folder: pathlib.Path,
    live: Sequence[tuple[str, CopyRecord]],
    targets: Mapping[str, Target],
) -> str:
    """Where the global memories are, one short line per standing memory, and
    the task groups the rest were learned in. Every session loads this, so it
    holds no memory text and stays within :data:`RULES_MAX_BYTES`."""
    standing, groups = _split_global(_newest_first(live, targets))
    parts = [
        RULES_HEADER
        + "\nThese memories are about the person, or were learned outside any project. "
        f"Their files are in `{folder}`; read one when its line is relevant to the task.\n"
    ]
    tail = ""
    if groups:
        tail = (
            "\n## Learned in specific tasks\n\n"
            f"`{folder / INDEX_NAME}` lists these by topic; when the task matches a topic, "
            f"read that list and then the files it names. Topics: {_topics_line(groups)}.\n"
        )
    size = len(parts[0].encode("utf-8")) + len(tail.encode("utf-8"))
    if standing:
        heading = f"\n## {STANDING_HEADING}\n\n"
        parts.append(heading)
        size += len(heading.encode("utf-8"))
        more = f"- …and {{}} more, listed in `{folder / INDEX_NAME}`.\n"
        # Room for the line naming the rest, should any be left out.
        budget = RULES_MAX_BYTES - len(more.format(len(standing)).encode("utf-8"))
        lines = [f"- {_rules_text(target.entry)} ({name})\n" for target, name in standing]
        if size + sum(len(line.encode("utf-8")) for line in lines) <= RULES_MAX_BYTES:
            budget = RULES_MAX_BYTES
        listed = 0
        for line in lines:
            if size + len(line.encode("utf-8")) > budget:
                break
            parts.append(line)
            size += len(line.encode("utf-8"))
            listed += 1
        if listed < len(standing):
            parts.append(more.format(len(standing) - listed))
    parts.append(tail)
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
