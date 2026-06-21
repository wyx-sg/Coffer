"""Native per-project memory — where a coding agent keeps its *own* memory.

Distinct from the curated config-file allowlist (``config_files.py``, which
covers instructions like ``CLAUDE.md``) and from Coffer's own knowledge/memory
substrate. Claude Code keeps a per-project memory store at
``<config_dir>/projects/<slug>/memory/*.md`` — a directory of individual fact
files plus a ``MEMORY.md`` index. Codex and the other supported agents have no
known native per-project memory layout, so they expose nothing here.

This module is pure value-level logic: the per-type layout table and a lossy
slug decoder. The on-disk ``memory_dir`` is the real identity of a store; the
decoded label/path are best-effort display sugar only.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.domain.agent.types import AgentType


@dataclass(frozen=True)
class NativeMemoryLayout:
    """Where an agent's native per-project memory lives, relative to its
    config dir: ``<config_dir>/<projects_subdir>/<slug>/<memory_subdir>``."""

    projects_subdir: str
    memory_subdir: str


def native_memory_layout_for(agent_type: AgentType) -> NativeMemoryLayout | None:
    """The native-memory layout for ``agent_type``, or ``None`` if it has none.

    Only Claude Code has a known per-project memory layout
    (``projects/<slug>/memory``). Every other agent type returns ``None`` →
    the caller surfaces an empty list.
    """
    if agent_type is AgentType.CLAUDE_CODE:
        return NativeMemoryLayout(projects_subdir="projects", memory_subdir="memory")
    return None


def decode_project_slug(slug: str) -> tuple[str, str | None]:
    """Best-effort decode of a project slug into ``(label, path)``.

    Claude Code names each project directory by replacing ``/`` with ``-`` in
    the project's absolute path (e.g. ``/Users/xing/Coffer`` →
    ``-Users-xing-Coffer``). A leading ``-`` therefore marks an absolute path.

    This is **lossy by design**: a path segment that itself contained a ``-``
    is indistinguishable from a separator, so the reconstructed path can be
    wrong. The ``memory_dir`` is the store's real identity; the returned
    label/path are only for display. When the slug carries no usable segments,
    returns ``(slug, None)``.
    """
    segments = [s for s in slug.split("-") if s]
    if not segments:
        return (slug, None)
    body = "/".join(segments)
    path = "/" + body if slug.startswith("-") else body
    return (segments[-1], path)


@dataclass(frozen=True)
class ParsedNativeFact:
    """One native-memory fact file parsed into the fields a memory write needs.

    Pure value object: the ``name``/``description``/``type``/``originSessionId``
    frontmatter (with the body) of a single ``projects/<slug>/memory/*.md`` file,
    normalised so the import service can hand it straight to a memory write. Lives
    in ``domain`` so the application layer can name it without importing the infra
    parser (Contract 2b)."""

    name: str
    description: str
    body: str
    type: str | None
    origin_session_id: str | None


@dataclass(frozen=True)
class NativeMemoryStore:
    """One agent-owned per-project memory store on disk.

    ``memory_dir`` is the source of truth; ``project_label`` / ``project_path``
    are best-effort, lossily decoded from ``slug`` (see ``decode_project_slug``).
    """

    project_label: str
    project_path: str | None
    slug: str
    memory_dir: str
    item_count: int
