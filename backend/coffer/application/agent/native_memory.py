"""Discover an agent's EXISTING native memory on disk (read-only).

Claude Code keeps per-project memory under ``<config_dir>/projects/<slug>/memory/``
(one ``.md`` per fact + a regenerated ``MEMORY.md``). Before Coffer takes a
project over (projection / symlink), that memory lives only there — invisible to
Coffer. This module scans for it so the UI can surface "N native memories not
yet managed by Coffer" and offer a takeover. Purely read-only: no mutation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Claude derives ``~/.claude/projects/<slug>`` by replacing each non-alnum char
# in the absolute project root with a single dash (runs NOT collapsed). Mirrors
# ``application.agent.projection.adapters.claude_project_slug``.
_NONALNUM = re.compile(r"[^A-Za-z0-9]")


def _name_slug(name: str) -> str:
    return _NONALNUM.sub("-", name)


def _full_slug(path: Path) -> str:
    return _NONALNUM.sub("-", str(path))


def decode_claude_slug(slug: str) -> Path | None:
    """Recover the absolute project root a Claude ``projects/<slug>`` came from.

    The slug encoding is LOSSY (``.``/``_``/space/``-`` all became ``-``), so we
    decode by walking the real filesystem: at each ``-`` boundary a token is
    either a path separator or an intra-name char. DFS tries both and returns
    the first reconstruction that exists on disk and round-trips to ``slug``
    (the round-trip guard guarantees a takeover symlink lands on THIS dir, never
    a wrong one). Returns ``None`` when no existing path matches."""
    if not slug.startswith("-"):
        return None

    def _children(d: Path) -> list[Path]:
        try:
            return [c for c in d.iterdir() if c.is_dir()]
        except OSError:
            return []

    def dfs(remaining: str, current: Path) -> Path | None:
        if not remaining:
            return current if _full_slug(current) == slug else None
        if not remaining.startswith("-"):
            return None
        rest = remaining[1:]
        for child in _children(current):
            cs = _name_slug(child.name)
            if rest == cs:
                return child if _full_slug(child) == slug else None
            if rest.startswith(cs):
                found = dfs(rest[len(cs) :], child)
                if found is not None:
                    return found
        return None

    return dfs(slug, Path("/"))


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
