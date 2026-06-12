"""Discover an agent's EXISTING native memory on disk (read-only).

Claude Code keeps per-project memory under ``<config_dir>/projects/<slug>/memory/``
(one ``.md`` per fact + a regenerated ``MEMORY.md``). Before Coffer takes a
project over (projection / symlink), that memory lives only there — invisible to
Coffer. This module scans for it so the UI can surface "N native memories not
yet managed by Coffer" and offer a takeover. Purely read-only: no mutation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class NativeMemoryProject:
    """One project's native memory directory under an agent's config dir."""

    slug: str
    memory_dir: str
    fact_count: int
    #: True when the dir is already a symlink (Coffer has taken it over).
    managed: bool


def scan_claude_native_memory(config_dir: Path) -> list[NativeMemoryProject]:
    """Scan ``<config_dir>/projects/*/memory`` for native memory.

    Returns one entry per project that has a ``memory`` dir, with its fact count
    and whether it is already a Coffer-managed symlink. Never mutates."""
    projects_dir = config_dir / "projects"
    if not projects_dir.is_dir():
        return []
    out: list[NativeMemoryProject] = []
    for slug_dir in sorted(projects_dir.iterdir()):
        if not slug_dir.is_dir():
            continue
        mem = slug_dir / "memory"
        if not mem.exists():
            continue
        managed = mem.is_symlink()
        facts = [p for p in mem.glob("*.md") if p.name != "MEMORY.md"]
        if not facts and not managed:
            continue
        out.append(
            NativeMemoryProject(
                slug=slug_dir.name,
                memory_dir=str(mem),
                fact_count=len(facts),
                managed=managed,
            )
        )
    return out
