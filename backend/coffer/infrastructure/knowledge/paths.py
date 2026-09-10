"""On-disk layout for the knowledge substrate.

Sole owner of path construction. One layout, one root:
``~/.coffer/knowledge/<scope>/`` — where ``<scope>`` is the resource name
(``global``, ``project-<ULID>``, or a named collection). Inside a scope dir:

- ``notes/``     what an agent or the user wrote (one markdown file each)
- ``docs/``      ingested documents (the normalized Markdown)
- ``.raw/``      the ingested originals (hidden, so grep skips them)
- ``.history/``  pre-rewrite copies kept by the tidy pass (hidden, likewise)

Two content lanes and two hidden archives, nothing else. The archives are
dot-prefixed so ripgrep skips them: ``coffer__grep`` must never return an
ingested original, or a superseded revision, alongside the live file.

``$COFFER_KNOWLEDGE_ROOT`` overrides the root for tests. Every name that
becomes a path segment goes through a traversal guard.
"""

from __future__ import annotations

import os
import pathlib
import re

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


def _child(parent: pathlib.Path, name: str, label: str) -> pathlib.Path:
    """A fixed-name subdirectory of a scope dir, traversal-checked."""
    candidate = (parent / name).resolve()
    if not candidate.is_relative_to(parent.resolve()):
        raise ValueError(f"{label} dir escapes the scope dir")
    return parent / name


def _leaf(parent: pathlib.Path, slug: str, label: str) -> pathlib.Path:
    """``<parent>/<slug>.md``, with ``slug`` guarded as one safe segment."""
    _safe_segment(slug, label)
    candidate = (parent / f"{slug}.md").resolve()
    if not candidate.is_relative_to(parent.resolve()):
        raise ValueError(f"{label} {slug!r} escapes {parent}")
    return parent / f"{slug}.md"


# --- the one root + the scope dir -------------------------------------------


def knowledge_root() -> pathlib.Path:
    """``~/.coffer/knowledge/`` (override via ``$COFFER_KNOWLEDGE_ROOT``)."""
    override = os.environ.get("COFFER_KNOWLEDGE_ROOT")
    if override:
        return pathlib.Path(override).expanduser()
    return _expand_home() / ".coffer" / "knowledge"


def scope_dir(scope_name: str) -> pathlib.Path:
    """``~/.coffer/knowledge/<scope>/`` for a scope's resource name."""
    return _guard(knowledge_root(), scope_name, "knowledge scope")


# --- the two content lanes --------------------------------------------------


def docs_dir(scope_name: str) -> pathlib.Path:
    """``<scope>/docs/`` — the normalized Markdown of ingested documents."""
    return scope_dir(scope_name) / "docs"


def doc_path(scope_name: str, doc_id: str) -> pathlib.Path:
    """Path of the normalized markdown ``docs/<doc-id>.md``."""
    return _leaf(docs_dir(scope_name), doc_id, "doc id")


def notes_dir(store_dir: pathlib.Path) -> pathlib.Path:
    """The ``notes/`` lane — everything an agent or the user wrote.

    A write lands here directly. There is no staging inbox and no later
    promotion into a separate topic-doc lane: the tidy pass merges and rewrites
    notes in place, so a note is a note however recently it was written.
    """
    return _child(store_dir, "notes", "notes")


def note_path(store_dir: pathlib.Path, slug: str) -> pathlib.Path:
    """Path of one note ``<store_dir>/notes/<slug>.md``."""
    return _leaf(notes_dir(store_dir), slug, "note slug")


# --- the hidden archives ----------------------------------------------------


def raw_dir(scope_name: str) -> pathlib.Path:
    """``<scope>/.raw/`` — the ingested originals, kept for re-conversion.

    Dot-prefixed deliberately: grep runs over the whole scope dir, and ripgrep
    skips hidden entries, so an original never shows up as a second hit
    alongside the Markdown that was converted from it.
    """
    return scope_dir(scope_name) / ".raw"


def raw_path(scope_name: str, doc_id: str, ext: str) -> pathlib.Path:
    """Path of the original upload ``.raw/<doc-id>.<ext>``."""
    _safe_segment(doc_id, "doc id")
    d = raw_dir(scope_name)
    bare_ext = ext.lstrip(".")
    if bare_ext:
        # A slashed/traversing ext (from an upload filename) would otherwise nest
        # subdirs inside .raw/; constrain it to a single safe segment.
        _safe_segment(bare_ext, "raw extension")
    clean_ext = ext if ext.startswith(".") else f".{ext}" if ext else ""
    candidate = (d / f"{doc_id}{clean_ext}").resolve()
    if not candidate.is_relative_to(d.resolve()):
        raise ValueError(f"raw file for {doc_id!r}{clean_ext!r} escapes the raw dir")
    return d / f"{doc_id}{clean_ext}"


def history_dir(store_dir: pathlib.Path) -> pathlib.Path:
    """``<store>/.history/`` — the note revisions the tidy pass replaced.

    The tidy pass runs unattended and lets an LLM merge and rewrite notes, so
    every overwrite archives the prior revision here first. Hidden, and a
    sibling of ``.raw/`` rather than a child of ``notes/``, so the lane scan
    and grep both pass it by without needing to know it exists.
    """
    return _child(store_dir, ".history", "history")


def history_path(store_dir: pathlib.Path, name: str) -> pathlib.Path:
    """``<store>/.history/<name>.md``, guarded as a single safe segment."""
    return _leaf(history_dir(store_dir), name, "history name")


# --- generic ----------------------------------------------------------------


def fact_path(store_dir: pathlib.Path, slug: str) -> pathlib.Path:
    """Path of a per-note markdown file ``<store_dir>/<slug>.md``.

    Takes the lane dir as an argument rather than deriving it, so the file I/O
    layer can address a note by the directory it already resolved.
    """
    _safe_segment(slug, "fact slug")
    candidate = (store_dir / f"{slug}.md").resolve()
    if not candidate.is_relative_to(store_dir.resolve()):
        raise ValueError(f"fact slug {slug!r} escapes the store dir")
    return store_dir / f"{slug}.md"
