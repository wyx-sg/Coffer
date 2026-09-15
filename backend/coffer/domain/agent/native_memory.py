"""Native per-project memory — where a coding agent keeps its *own* memory.

Distinct from the curated config-file allowlist (``config_files.py``, which
covers instructions like ``CLAUDE.md``) and from Coffer's own knowledge layer.
Claude Code keeps a per-project memory store at
``<config_dir>/projects/<slug>/memory/*.md`` — a directory of individual fact
files plus a ``MEMORY.md`` index. Codex instead keeps a single *global*
task-grouped store (``memories/MEMORY.md``, see :class:`CodexGlobalLayout` and
``codex_memory``); the other supported agents have no known native memory layout
and expose nothing here.

This module is pure value-level logic: the per-type layout table, the rule for
whether a directory IS one of these stores, a lossy slug decoder, and the value
shapes a store's contents take. The on-disk ``memory_dir`` is the real identity
of a store; the decoded label/path are best-effort display sugar only. The
surface is read-only — Coffer lists these stores, shows what is in them, and
never writes them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from coffer.domain.agent.types import AgentType


class ScannedStore(NamedTuple):
    """Raw result of scanning one native-memory store on disk.

    ``project_path`` is the store's *real* project directory when the infra
    adapter could recover it (e.g. from a session transcript's ``cwd`` field);
    ``None`` when unknown, in which case the caller decodes a best-effort path
    from ``slug``. The slug encoding is lossy (Claude Code collapses every
    non-alphanumeric character — ``/``, ``.``, ``_``, and so on — to ``-``),
    so the decoded path is wrong whenever a path segment or the home dir
    contained one of those characters — hence the cwd-derived
    ``project_path`` is preferred when available, and :func:`resolve_project_slug`
    (an FS-aware decode) beats the naive :func:`decode_project_slug` whenever
    neither is.
    """

    slug: str
    memory_dir: str
    item_count: int
    project_path: str | None


@dataclass(frozen=True)
class NativeMemoryLayout:
    """Where an agent's native per-project memory lives, relative to its
    config dir: ``<config_dir>/<projects_subdir>/<slug>/<memory_subdir>``."""

    projects_subdir: str
    memory_subdir: str


@dataclass(frozen=True)
class CodexGlobalLayout:
    """Codex's single *global* task-grouped memory store, at
    ``<config_dir>/<memory_subdir>/<index_file>`` (``~/.codex/memories/MEMORY.md``).

    Unlike the per-project :class:`NativeMemoryLayout`, one document routes many
    projects via per-Task-Group ``cwd`` annotations (see
    ``coffer.domain.agent.codex_memory.parse_codex_memory``). The infrastructure
    layer parses it into one store row per distinct cwd."""

    memory_subdir: str
    index_file: str


def native_memory_layout_for(
    agent_type: AgentType,
) -> NativeMemoryLayout | CodexGlobalLayout | None:
    """The native-memory layout for ``agent_type``, or ``None`` if it has none.

    Claude Code has a per-project layout (``projects/<slug>/memory``); Codex has
    a single global task-grouped store (``memories/MEMORY.md``). Every other
    agent type returns ``None`` → the caller surfaces an empty list.
    """
    if agent_type is AgentType.CLAUDE_CODE:
        return NativeMemoryLayout(projects_subdir="projects", memory_subdir="memory")
    if agent_type is AgentType.CODEX:
        return CodexGlobalLayout(memory_subdir="memories", index_file="MEMORY.md")
    return None


def is_native_memory_dir(
    layout: NativeMemoryLayout | CodexGlobalLayout | None,
    config_dir: Path,
    candidate: Path,
) -> bool:
    """Whether *candidate* is a store directory this layout would have listed.

    The rule that lets a store's folder be browsed without letting an arbitrary
    directory be. The scan (:meth:`FileNativeMemoryScanner.scan`) walks the
    layout to *find* stores; this states the same shape as a predicate so a
    ``memory_dir`` coming back from a client can be checked against it for a few
    microseconds instead of by re-running a scan that takes seconds.

    Deliberately exact rather than "somewhere under the config dir": a store is
    ``<projects>/<slug>/<memory>`` for the per-project layout and the single
    ``<memories>`` directory for Codex's global one. Anything else in the
    agent's config dir — its transcripts, its settings, its plugin cache — is
    not a memory store and must not be readable through a surface that only
    claims to show memory.

    *candidate* and *config_dir* are expected to be resolved already, so a
    symlink pointing out of the config dir fails here rather than being
    followed.
    """
    if layout is None:
        return False
    if isinstance(layout, CodexGlobalLayout):
        return candidate == config_dir / layout.memory_subdir
    return (
        candidate.name == layout.memory_subdir
        and candidate.parent.parent == config_dir / layout.projects_subdir
    )


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


def _encode(name: str) -> str:
    """Claude Code's own path-component encoding, applied to one real name.

    Every character that is not an ASCII letter or digit becomes ``-`` — not
    just ``/``. A real example: the slug ``-Users-yuxing-wu`` decodes to
    ``/Users/yuxing.wu`` — the dot in the home directory's own name was
    encoded exactly the same way the ``/`` separators were. That means a
    slug's dashes are not reliably separators, dots, or literal dashes
    already in a name — the encoding is lossy, and no amount of cleverness
    recovers it from the slug string alone.
    """
    return "".join(ch if ch.isalnum() and ch.isascii() else "-" for ch in name)


def _walk(current: str, remaining: str, list_dirs: Callable[[str], list[str]]) -> str | None:
    """Consume ``remaining`` one real subdirectory at a time, or fail.

    What recovers the original path is the filesystem: a real directory's
    name, run through :func:`_encode`, either is or is not a prefix of what
    is left of the slug. So this walks down from ``current`` (an absolute
    path, ``""`` standing for ``/``) and, at each level, asks every real
    subdirectory ``list_dirs`` reports that question, rather than guessing
    where the original separators were.

    Ties are broken by preferring the longest immediate match, with
    backtracking into the runner-up when the greedy choice turns out to be a
    dead end — the same slug prefix can occasionally be produced by two real
    sibling directories (e.g. ``ab-cd`` and ``ab``, when only the latter has
    a child that finishes resolving the rest of the slug).
    """
    if not remaining:
        return current or "/"
    candidates: list[tuple[int, str]] = []
    for name in list_dirs(current or "/"):
        encoded = _encode(name)
        if not encoded:
            continue
        if remaining == encoded or remaining.startswith(encoded + "-"):
            candidates.append((len(encoded), name))
    candidates.sort(key=lambda pair: -pair[0])
    for consumed, name in candidates:
        rest = remaining[consumed:]
        rest = rest[1:] if rest.startswith("-") else rest
        child = f"{current}/{name}" if current else f"/{name}"
        result = _walk(child, rest, list_dirs)
        if result is not None:
            return result
    return None


def resolve_project_slug(
    slug: str, list_dirs: Callable[[str], list[str]]
) -> tuple[str, str | None]:
    """FS-aware decode of a project slug into ``(label, path)``.

    Claude Code's encoding (:func:`_encode`) collapses every non-alphanumeric
    character to ``-``, so a slug's dashes are not reliably separators, dots,
    underscores, or literal dashes already in a name — the naive
    :func:`decode_project_slug` gets this wrong whenever a real path segment
    (or the home directory's own name) contains anything but a letter, digit
    or ``/``. What disambiguates it is the filesystem itself: this walks down
    from ``/``, and at each level asks every real subdirectory ``list_dirs``
    reports whether its *encoded* name is a prefix of what is left of the
    slug — consuming that many encoded characters (not a naive dash-count),
    which is what lets a real ``yuxing.wu`` (9 characters) consume the slug's
    ``yuxing-wu`` (9 characters, one dash where the dot was) correctly. Ties
    prefer the longest immediate match, backtracking into the runner-up when
    the greedy choice is a dead end (see :func:`_walk`).

    Falls back to the lossy :func:`decode_project_slug` when the walk cannot
    proceed at all — a step in the path was renamed or deleted, the project
    no longer exists on disk, or the slug carries no usable segments. That
    fallback is lossy in exactly the ways described above, but it is the
    best guess available once there is nothing left on disk to check
    against. ``list_dirs`` is injected (given an absolute path, returns the
    names of its real subdirectories, or ``[]`` when it cannot be listed) so
    this stays pure/testable — the concrete adapter lives in infrastructure.
    """
    if not slug.startswith("-"):
        return decode_project_slug(slug)
    body = slug[1:]
    if not body:
        return decode_project_slug(slug)
    resolved = _walk("", body, list_dirs)
    if resolved is None:
        return decode_project_slug(slug)
    label = resolved.rsplit("/", 1)[-1] or resolved
    return (label, resolved)


@dataclass
class MemoryFileNode:
    """One entry in a native-memory store's directory tree.

    ``path`` is POSIX and relative to the store directory (``""`` for the root
    node), so nothing in a tree hands a caller an absolute path it could then
    ask to read — the store directory is supplied separately and checked once.
    ``size`` is the file's byte size (``None`` for directories) and
    ``truncated`` marks a directory whose descendants were clipped at the walk
    depth bound.
    """

    name: str
    path: str
    type: str  # "file" | "dir"
    size: int | None = None
    children: list[MemoryFileNode] = field(default_factory=list)
    truncated: bool = False


@dataclass(frozen=True)
class MemoryFileContent:
    """One file from a native-memory store, as a read-only preview shows it.

    No fingerprint, unlike the skill file viewer's equivalent: a fingerprint
    exists to make a later write conditional, and there is no write here. The
    agent owns these files and rewrites them on its own schedule; the honest way
    to change one is to open it in a real editor, which the surface offers.
    """

    path: str
    content: str  # empty when ``binary``
    truncated: bool
    binary: bool
    size: int


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
