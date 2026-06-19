"""On-disk layout for the shared knowledge substrate.

Sole owner of path construction for both the KB face
(``~/.coffer/knowledge/<kb>/{docs,raw}/``) and the memory face
(``~/.coffer/memory/{global,projects/<ulid>}/``), with ``$COFFER_*_ROOT``
overrides for tests and path-traversal guards on every name.
"""

from __future__ import annotations

import os
import pathlib
import re

from coffer.domain.knowledge.document import WORKSPACE_GLOBAL_PROJECT_ID

# Names that would resolve to a parent dir or the root itself are unsafe for
# rmtree / write targets. Surfaces already constrain resource names; this is
# defense-in-depth for any caller that bypasses the surface validator.
_DOTS_ONLY = re.compile(r"^\.+$")
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def _expand_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME", "~")).expanduser()


def _guard(root: pathlib.Path, name: str, label: str) -> pathlib.Path:
    """Resolve ``root / name`` and refuse traversal / all-dot names."""
    if not name or _DOTS_ONLY.fullmatch(name) or not _SAFE_SEGMENT.fullmatch(name):
        raise ValueError(f"invalid {label} name: {name!r}")
    candidate = root / name
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"{label} name {name!r} escapes {label} root")
    return candidate


def _safe_segment(value: str, label: str) -> str:
    """Refuse a value that isn't a single safe path segment.

    Root-escape is already blocked downstream, but a slash-containing value
    (e.g. an ``ext`` derived from an upload filename) would create nested
    subdirs *inside* the root. Constrain to one segment as defense-in-depth.
    """
    if not value or _DOTS_ONLY.fullmatch(value) or not _SAFE_SEGMENT.fullmatch(value):
        raise ValueError(f"invalid {label}: {value!r}")
    return value


# --- knowledge base layout --------------------------------------------------


def knowledge_root() -> pathlib.Path:
    """``~/.coffer/knowledge/`` (override via ``$COFFER_KNOWLEDGE_ROOT``)."""
    override = os.environ.get("COFFER_KNOWLEDGE_ROOT")
    if override:
        return pathlib.Path(override).expanduser()
    return _expand_home() / ".coffer" / "knowledge"


def kb_dir(name: str) -> pathlib.Path:
    return _guard(knowledge_root(), name, "knowledge base")


def kb_store_dir(name: str, project_id: str = WORKSPACE_GLOBAL_PROJECT_ID) -> pathlib.Path:
    """The on-disk root for one document scope of a KB (ADR-030).

    Global scope is the KB root itself (``knowledge/<kb>/``, leaving existing
    global documents in place — back-compatible); a project scope nests under
    ``knowledge/<kb>/projects/<project-ulid>/``.
    """
    base = kb_dir(name)
    if project_id == WORKSPACE_GLOBAL_PROJECT_ID:
        return base
    return _guard(base / "projects", project_id, "project")


def docs_dir(name: str, project_id: str = WORKSPACE_GLOBAL_PROJECT_ID) -> pathlib.Path:
    return kb_store_dir(name, project_id) / "docs"


def raw_dir(name: str, project_id: str = WORKSPACE_GLOBAL_PROJECT_ID) -> pathlib.Path:
    return kb_store_dir(name, project_id) / "raw"


def doc_path(name: str, doc_id: str, project_id: str = WORKSPACE_GLOBAL_PROJECT_ID) -> pathlib.Path:
    """Path of the normalized markdown ``[projects/<ulid>/]docs/<doc-id>.md``."""
    _safe_segment(doc_id, "doc id")
    d = docs_dir(name, project_id)
    candidate = (d / f"{doc_id}.md").resolve()
    if not candidate.is_relative_to(d.resolve()):
        raise ValueError(f"doc id {doc_id!r} escapes the docs dir")
    return d / f"{doc_id}.md"


def raw_path(
    name: str, doc_id: str, ext: str, project_id: str = WORKSPACE_GLOBAL_PROJECT_ID
) -> pathlib.Path:
    """Path of the original upload ``[projects/<ulid>/]raw/<doc-id>.<ext>``."""
    _safe_segment(doc_id, "doc id")
    d = raw_dir(name, project_id)
    bare_ext = ext.lstrip(".")
    if bare_ext:
        # A slashed/traversing ext (from an upload filename) would otherwise nest
        # subdirs inside raw/; constrain it to a single safe segment.
        _safe_segment(bare_ext, "raw extension")
    clean_ext = ext if ext.startswith(".") else f".{ext}" if ext else ""
    candidate = (d / f"{doc_id}{clean_ext}").resolve()
    if not candidate.is_relative_to(d.resolve()):
        raise ValueError(f"raw file for {doc_id!r}{clean_ext!r} escapes the raw dir")
    return d / f"{doc_id}{clean_ext}"


# --- memory layout ----------------------------------------------------------


def memory_root() -> pathlib.Path:
    """``~/.coffer/memory/`` (override via ``$COFFER_MEMORY_ROOT``)."""
    override = os.environ.get("COFFER_MEMORY_ROOT")
    if override:
        return pathlib.Path(override).expanduser()
    return _expand_home() / ".coffer" / "memory"


def memory_global_dir() -> pathlib.Path:
    """The global scope store dir (sentinel project id)."""
    return memory_root() / "global"


def memory_projects_dir() -> pathlib.Path:
    return memory_root() / "projects"


def memory_project_dir(project_id: str) -> pathlib.Path:
    """Per-project store dir ``projects/<project-ulid>/``."""
    return _guard(memory_projects_dir(), project_id, "project")


def memory_store_dir(project_id: str) -> pathlib.Path:
    """Resolve a memory store dir from its ``project_id`` (sentinel ⇒ global)."""
    if project_id == WORKSPACE_GLOBAL_PROJECT_ID:
        return memory_global_dir()
    return memory_project_dir(project_id)


def memory_index_path() -> str:
    return "MEMORY.md"


def fact_path(store_dir: pathlib.Path, slug: str) -> pathlib.Path:
    """Path of a per-fact markdown file ``<store_dir>/<slug>.md``."""
    _safe_segment(slug, "fact slug")
    candidate = (store_dir / f"{slug}.md").resolve()
    if not candidate.is_relative_to(store_dir.resolve()):
        raise ValueError(f"fact slug {slug!r} escapes the store dir")
    return store_dir / f"{slug}.md"
