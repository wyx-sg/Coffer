"""On-disk layout for the knowledge substrate.

Sole owner of path construction. One layout, one root:
``~/.coffer/knowledge/<scope>/`` — where ``<scope>`` is the resource name
(``global``, ``project-<ULID>``, or a named collection). Inside a scope dir:

- ``knowledge/``   topic docs + ``knowledge/inbox/`` (freshly written entries)
- ``rules/``       behavioural rules
- ``handoff/``     per-branch working state
- ``superseded/``  retired topic docs
- ``inbox/``       ingested documents (the normalized Markdown)
- ``.raw/``        the ingested originals (hidden, so grep skips them)

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


# --- the ingestion lane -----------------------------------------------------


def docs_dir(scope_name: str) -> pathlib.Path:
    """``<scope>/inbox/`` — the normalized Markdown of ingested documents."""
    return scope_dir(scope_name) / "inbox"


def raw_dir(scope_name: str) -> pathlib.Path:
    """``<scope>/.raw/`` — the ingested originals, kept for re-conversion.

    Dot-prefixed deliberately: grep runs over the whole scope dir, and ripgrep
    skips hidden entries, so an original never shows up as a second hit
    alongside the Markdown that was converted from it.
    """
    return scope_dir(scope_name) / ".raw"


def doc_path(scope_name: str, doc_id: str) -> pathlib.Path:
    """Path of the normalized markdown ``inbox/<doc-id>.md``."""
    return _leaf(docs_dir(scope_name), doc_id, "doc id")


def raw_path(scope_name: str, doc_id: str, ext: str) -> pathlib.Path:
    """Path of the original upload ``raw/<doc-id>.<ext>``."""
    _safe_segment(doc_id, "doc id")
    d = raw_dir(scope_name)
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


# --- the entry lanes --------------------------------------------------------


def fact_path(store_dir: pathlib.Path, slug: str) -> pathlib.Path:
    """Path of a per-fact markdown file ``<store_dir>/<slug>.md``."""
    _safe_segment(slug, "fact slug")
    candidate = (store_dir / f"{slug}.md").resolve()
    if not candidate.is_relative_to(store_dir.resolve()):
        raise ValueError(f"fact slug {slug!r} escapes the store dir")
    return store_dir / f"{slug}.md"


def knowledge_dir(store_dir: pathlib.Path) -> pathlib.Path:
    """The ``knowledge/`` lane of a memory store — the semantic memory the
    ``recall`` glob searches (inbox items + organized topic docs)."""
    candidate = (store_dir / "knowledge").resolve()
    if not candidate.is_relative_to(store_dir.resolve()):
        raise ValueError("knowledge dir escapes the store dir")
    return store_dir / "knowledge"


def inbox_dir(store_dir: pathlib.Path) -> pathlib.Path:
    """The ``knowledge/inbox/`` subdir — freshly-remembered, not-yet-organized
    items. The consolidation organizer drains it into topic docs."""
    return knowledge_dir(store_dir) / "inbox"


def inbox_item_path(store_dir: pathlib.Path, slug: str) -> pathlib.Path:
    """Path of a per-item file ``<store_dir>/knowledge/inbox/<slug>.md``."""
    _safe_segment(slug, "inbox item slug")
    d = inbox_dir(store_dir)
    candidate = (d / f"{slug}.md").resolve()
    if not candidate.is_relative_to(d.resolve()):
        raise ValueError(f"inbox item slug {slug!r} escapes the inbox dir")
    return d / f"{slug}.md"


def topic_path(store_dir: pathlib.Path, slug: str) -> pathlib.Path:
    """Path of an organized topic doc ``<store_dir>/knowledge/<slug>.md``.

    Topic docs live alongside ``inbox/`` in the ``knowledge/`` lane (so ``recall``
    finds them) but are NOT inbox items. The organizer writes them; the slug is
    guarded as a single safe segment (no traversal, no nested dirs)."""
    _safe_segment(slug, "topic slug")
    d = knowledge_dir(store_dir)
    candidate = (d / f"{slug}.md").resolve()
    if not candidate.is_relative_to(d.resolve()):
        raise ValueError(f"topic slug {slug!r} escapes the knowledge dir")
    return d / f"{slug}.md"


def knowledge_index_path(store_dir: pathlib.Path) -> pathlib.Path:
    """The ``knowledge/INDEX.md`` review catalog (regenerated by the organizer,
    excluded from recall + the sync mirror)."""
    return knowledge_dir(store_dir) / "INDEX.md"


def consolidation_log_path(store_dir: pathlib.Path) -> pathlib.Path:
    """The store-root ``consolidation-log.md`` append-only changelog. It sits at
    the store ROOT (outside ``knowledge/``) so it is automatically excluded from
    recall; it is also excluded from the sync mirror (machine-local)."""
    return store_dir / "consolidation-log.md"


def superseded_dir(store_dir: pathlib.Path) -> pathlib.Path:
    """The store-root ``superseded/`` tombstone — topic docs retired by the reorg
    pass. At the store ROOT (outside ``knowledge/``) so it is excluded from recall
    like ``handoff/``; recoverable, and it DOES sync (source-of-truth history)."""
    return store_dir / "superseded"


def superseded_path(store_dir: pathlib.Path, name: str) -> pathlib.Path:
    """``<store>/superseded/<name>.md``, guarded as a single safe segment."""
    _safe_segment(name, "superseded name")
    d = superseded_dir(store_dir)
    candidate = (d / f"{name}.md").resolve()
    if not candidate.is_relative_to(d.resolve()):
        raise ValueError(f"superseded name {name!r} escapes the superseded dir")
    return d / f"{name}.md"


def handoff_dir(store_dir: pathlib.Path) -> pathlib.Path:
    """The ``handoff/`` subdir of a memory store (working-state files live here,
    excluded from recall which globs only the store dir's top-level ``*.md``)."""
    candidate = (store_dir / "handoff").resolve()
    if not candidate.is_relative_to(store_dir.resolve()):
        raise ValueError("handoff dir escapes the store dir")
    return store_dir / "handoff"


def rules_dir(store_dir: pathlib.Path) -> pathlib.Path:
    """The store-root ``rules/`` dir — behavioural rules classified by the
    organizer. At the store ROOT (outside ``knowledge/``) so it is excluded from
    recall; it DOES sync (source-of-truth, like ``superseded/``)."""
    candidate = (store_dir / "rules").resolve()
    if not candidate.is_relative_to(store_dir.resolve()):
        raise ValueError("rules dir escapes the store dir")
    return store_dir / "rules"


def rules_path(store_dir: pathlib.Path) -> pathlib.Path:
    """Path of the default rules file ``<store_dir>/rules/rules.md`` — the bucket
    new rules append to before the autonomous split redistributes them."""
    return rules_dir(store_dir) / "rules.md"


def rule_file_path(store_dir: pathlib.Path, slug: str) -> pathlib.Path:
    """Path of a per-category rules file ``<store_dir>/rules/<slug>.md``.

    The autonomous split (spec 007 amendment 2026-06-22) groups rules into these
    by topic once ``rules.md`` grows past the threshold. The slug is guarded as a
    single safe segment (no traversal, no nested dirs)."""
    _safe_segment(slug, "rules slug")
    d = rules_dir(store_dir)
    candidate = (d / f"{slug}.md").resolve()
    if not candidate.is_relative_to(d.resolve()):
        raise ValueError(f"rules slug {slug!r} escapes the rules dir")
    return d / f"{slug}.md"


def handoff_path(store_dir: pathlib.Path, branch_slug: str) -> pathlib.Path:
    """Path of a per-branch handoff file ``<store_dir>/handoff/<branch-slug>.md``."""
    _safe_segment(branch_slug, "branch slug")
    d = handoff_dir(store_dir)
    candidate = (d / f"{branch_slug}.md").resolve()
    if not candidate.is_relative_to(d.resolve()):
        raise ValueError(f"branch slug {branch_slug!r} escapes the handoff dir")
    return d / f"{branch_slug}.md"
