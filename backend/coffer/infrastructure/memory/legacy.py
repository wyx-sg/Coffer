"""Removing what an older build wrote into the agents' own memory (ADR
keep-memory-in-one-place-agents-write-themselves).

Earlier builds copied the hub into each agent's native memory: a marked block
at the end of each Claude Code project's ``MEMORY.md``, and an ``extensions/
coffer/`` folder in each Codex memory folder. A session now gets the hub from
Coffer's session-start hook, so those copies would hand it every memory twice.
This removes them, and the two machine-local files the old sync kept. It
touches only what Coffer wrote: everything outside the markers, and every file
an agent wrote, stays byte for byte. Idempotent and cheap, so it runs at every
daemon start; a failure is logged and never stops the daemon.
"""

from __future__ import annotations

import logging
import pathlib
import shutil
from collections.abc import Iterable

from coffer.infrastructure.memory.frontmatter import atomic_write
from coffer.infrastructure.vault.home import local_root

log = logging.getLogger(__name__)

BLOCK_BEGIN = "<!-- coffer:memory-sync:begin -->"
BLOCK_END = "<!-- coffer:memory-sync:end -->"
#: The machine-local files the old sync kept.
_LOCAL_FILES = ("memory-sync.json", "memory-sync-preview.json")


def strip_block(text: str) -> str | None:
    """``text`` without Coffer's marked block, or ``None`` when it has none."""
    begin = text.find(BLOCK_BEGIN)
    if begin < 0:
        return None
    end = text.find(BLOCK_END, begin)
    tail = text[end + len(BLOCK_END) :] if end >= 0 else ""
    head = text[:begin].rstrip("\n")
    rest = tail.lstrip("\n")
    joined = "\n\n".join(p for p in (head, rest.rstrip("\n")) if p)
    return f"{joined}\n" if joined else ""


def remove_claude_copies(config_dir: pathlib.Path) -> int:
    """Take Coffer's block out of every project's ``MEMORY.md``; a file left
    empty is deleted. The number of files changed."""
    changed = 0
    for index in sorted((config_dir / "projects").glob("*/memory/MEMORY.md")):
        try:
            text = index.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new = strip_block(text)
        if new is None:
            continue
        try:
            if new.strip():
                atomic_write(index, new)
            else:
                index.unlink()
            changed += 1
        except OSError:
            log.warning("memory.legacy.claude_failed path=%s", index, exc_info=True)
    return changed


def remove_codex_copies(config_dir: pathlib.Path) -> int:
    """Delete ``extensions/coffer/`` from every Codex memory folder. The
    number of folders removed."""
    removed = 0
    for folder in sorted(config_dir.glob("memories*/extensions/coffer")):
        try:
            if folder.is_dir() and not folder.is_symlink():
                shutil.rmtree(folder)
                removed += 1
        except OSError:
            log.warning("memory.legacy.codex_failed path=%s", folder, exc_info=True)
    return removed


def remove_sync_state(local: pathlib.Path | None = None) -> None:
    """Delete the old sync's ledger and pending preview."""
    base = local or local_root()
    for name in _LOCAL_FILES:
        try:
            (base / name).unlink(missing_ok=True)
        except OSError:
            log.warning("memory.legacy.state_failed name=%s", name, exc_info=True)


def remove_old_copies(config_dirs: Iterable[pathlib.Path]) -> None:
    """Everything above, for every registered agent's config directory
    (blocking; run it in a thread). Each layout is matched by its own path
    pattern, so a directory of another agent simply matches nothing."""
    for d in config_dirs:
        claude = remove_claude_copies(d)
        codex = remove_codex_copies(d)
        if claude or codex:
            log.info("memory.legacy.removed claude=%d codex=%d dir=%s", claude, codex, d)
    remove_sync_state()


__all__ = [
    "BLOCK_BEGIN",
    "BLOCK_END",
    "remove_claude_copies",
    "remove_codex_copies",
    "remove_old_copies",
    "remove_sync_state",
    "strip_block",
]
