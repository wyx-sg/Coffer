"""Writes hub entries into Claude Code as text it loads (spec memory "Write the
hub into Claude Code as text it loads", ADR
claude-code-reads-other-agents-memories-as-text).

Claude Code loads a project's ``MEMORY.md`` (its first 200 lines) in every
session in that project; it opens a memory's own file only when the model
decides to, which in practice it does not. So Coffer writes no file per
memory: a project's memories go, as text, into a marked block at the end of
the project's ``MEMORY.md`` in ``<config_dir>/projects/<slug>/memory/``, the
directory Claude Code keeps for a repository root (``slug`` is
:func:`coffer.domain.agent.native_memory.encode_slug` of the root, shared by
every worktree of it). Only the bytes between the markers change; the file is
backed up before each change.
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping, Sequence

from coffer.domain.agent.native_memory import encode_slug
from coffer.domain.memory.hub import check_segment
from coffer.domain.memory.native_writer import (
    STATUS_MISSING,
    STATUS_OK,
    AuxWrite,
    WriteLocation,
    WriterStatus,
)
from coffer.domain.memory.sync_plan import CopyRecord, Target
from coffer.infrastructure.memory import native_files
from coffer.infrastructure.memory.writers.claude_code_lines import INDEX_NAME, block_lines

BLOCK_BEGIN = "<!-- coffer:memory-sync:begin -->"
BLOCK_END = "<!-- coffer:memory-sync:end -->"


def memory_dir(config_dir: str, root: str) -> pathlib.Path:
    """Claude Code's memory directory for the repository at ``root``."""
    slug = check_segment(encode_slug(root.rstrip("/")))
    return pathlib.Path(config_dir) / "projects" / slug / "memory"


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

    def locations(self, config_dir: str) -> tuple[WriteLocation, ...]:
        """One location: the config directory itself."""
        return (WriteLocation("", config_dir),)

    def status(self, config_dir: str) -> WriterStatus:
        if not pathlib.Path(config_dir).is_dir():
            return WriterStatus(STATUS_MISSING, config_dir, "the config directory is not there")
        return WriterStatus(STATUS_OK, config_dir)

    def wants(self, target: Target) -> bool:
        # Every memory reaches Claude Code as a line of its project's block.
        return False

    def path_for(self, config_dir: str, target: Target, taken: set[str]) -> str:
        raise AssertionError("Claude Code holds no file per memory")

    def render(self, target: Target) -> str:
        raise AssertionError("Claude Code holds no file per memory")

    def aux(
        self,
        config_dir: str,
        copies: Mapping[str, CopyRecord],
        targets: Mapping[str, Target],
        inline: Sequence[Target],
    ) -> list[AuxWrite]:
        out: list[AuxWrite] = []
        # Every folder holding a block, so one whose last memory went is emptied.
        by_dir: dict[pathlib.Path, list[Target]] = {
            folder: [] for folder in _block_folders(config_dir)
        }
        for target in inline:
            by_dir.setdefault(memory_dir(config_dir, target.root), []).append(target)
        for folder, held in sorted(by_dir.items()):
            index = folder / INDEX_NAME
            current = native_files.read(index) or ""
            lines = block_lines(held, held[0].entry.project) if held else []
            new = replace_block(current, lines)
            if new != current:
                out.append(AuxWrite(str(index), new or None, backup=bool(current)))
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
    "BLOCK_END",
    "ClaudeCodeMemoryWriter",
    "memory_dir",
    "replace_block",
]
