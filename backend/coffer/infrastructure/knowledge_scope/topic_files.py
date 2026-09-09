"""On-disk I/O for the organizer's topic docs, INDEX, and the changelog.

The consolidation organizer (``application/memory/organizer.py``) drains the
``knowledge/inbox/`` into a small set of coherent topic documents
(``knowledge/<slug>.md``), maintains the ``knowledge/INDEX.md`` review catalog,
and appends to the store-root ``consolidation-log.md``. This module is the only
place that reads/writes those three file kinds — mirrors
``infrastructure/memory/files.py`` / ``handoff_files.py`` and delegates
frontmatter parse/render to the shared ``infrastructure.knowledge.frontmatter``
(the PyYAML owner).

A topic doc is overwrite-per-slug (the organizer always hands the LLM the prior
content and writes the merged whole back) and IS indexed for recall — it lives
in the ``knowledge/`` lane the recall glob descends into, unlike a handoff.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from coffer.infrastructure.knowledge.frontmatter import (
    render_frontmatter,
    split_frontmatter,
)
from coffer.infrastructure.knowledge.fs import atomic_write_text
from coffer.infrastructure.knowledge.paths import (
    consolidation_log_path,
    knowledge_dir,
    knowledge_index_path,
    superseded_dir,
    superseded_path,
    topic_path,
)

#: The lane's human review index — never itself a topic doc.
_INDEX_NAME = "INDEX.md"
#: Non-slug, non-segment chars collapse to a single hyphen for a filesystem-safe,
#: kebab-case slug. Matches the safe-segment alphabet in ``paths._SAFE_SEGMENT``.
_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(frozen=True)
class TopicDoc:
    """An organized topic document: the slug (its filename stem), the
    human-readable title/description (frontmatter), the full markdown body, and
    the timestamp of the last organizer write."""

    slug: str
    title: str
    description: str
    body: str
    updated_at: datetime


def topic_slug(title: str) -> str:
    """A filesystem-safe, kebab-case slug for a topic title.

    Lower-cases, collapses runs of unsafe chars to a single hyphen, and trims
    leading/trailing hyphens/dots. Falls back to ``"topic"`` when the title has
    no usable characters (e.g. all punctuation), so the result is always a valid
    single path segment that ``topic_path`` accepts."""
    slug = _SLUG_RE.sub("-", title.strip().lower()).strip("-.")
    return slug or "topic"


def write_topic_doc(path: Path, doc: TopicDoc) -> None:
    """Write (overwrite) a topic doc to ``path``: frontmatter + body.

    The organizer always passes the LLM the prior body to merge into, so an
    overwrite here is a merge-with-history, never a from-scratch clobber. The
    write is atomic so a crash never leaves a partial topic doc."""
    text = render_frontmatter(
        {
            # A topic doc lives in the knowledge lane — same ``kind`` header as a
            # per-fact file for a consistent on-disk format.
            "kind": "knowledge",
            "title": doc.title,
            "description": doc.description,
            "updated_at": doc.updated_at.isoformat(),
        },
        doc.body,
    )
    atomic_write_text(path, text)


def read_topic_doc(path: Path) -> TopicDoc | None:
    """Read + parse a topic doc, or ``None`` if it does not exist.

    Degrades gracefully on a hand-written doc that omits frontmatter keys:
    ``title`` falls back to the filename stem, ``description`` to the first body
    line, ``updated_at`` to the file mtime — so a human-authored topic doc still
    becomes a valid merge candidate."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, body = split_frontmatter(text)
    body = body.strip("\n")
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return TopicDoc(
        slug=path.stem,
        title=str(meta.get("title") or path.stem),
        description=str(meta.get("description") or _first_line(body)),
        body=body,
        updated_at=_parse_updated_at(meta.get("updated_at"), default=mtime),
    )


def list_topic_docs(store_dir: Path) -> list[TopicDoc]:
    """Every organized topic doc in the store's ``knowledge/`` lane.

    The lane's top-level ``*.md`` files EXCEPT ``INDEX.md`` (the review catalog)
    and EXCEPT the ``inbox/`` subdir (freshly-remembered items, not yet
    organized). The lane may not exist yet → an empty list, never an error.
    Sorted by slug for a deterministic INDEX ordering."""
    lane = knowledge_dir(store_dir)
    if not lane.exists():
        return []
    docs: list[TopicDoc] = []
    for path in sorted(lane.glob("*.md")):  # top-level only — never descends into inbox/
        if path.name == _INDEX_NAME:
            continue
        doc = read_topic_doc(path)
        if doc is not None:
            docs.append(doc)
    return docs


def render_index(docs: list[TopicDoc]) -> str:
    """Render the ``INDEX.md`` review catalog from the topic docs' frontmatter.

    One bullet per topic — ``- [<title>](<slug>.md) — <description>`` — sorted by
    slug for a stable, conflict-free file."""
    lines = ["# Memory — topic index", ""]
    for doc in sorted(docs, key=lambda d: d.slug):
        desc = f" — {doc.description}" if doc.description else ""
        lines.append(f"- [{doc.title}]({doc.slug}.md){desc}")
    return "\n".join(lines) + "\n"


def write_index(store_dir: Path, docs: list[TopicDoc]) -> None:
    """Regenerate the store's ``knowledge/INDEX.md`` from all topic docs."""
    path = knowledge_index_path(store_dir)
    atomic_write_text(path, render_index(docs))


def append_changelog(store_dir: Path, entry: str) -> None:
    """Append one human-readable line to the store-root ``consolidation-log.md``.

    Append-only and non-blocking: it is an audit trail, never a gate."""
    path = consolidation_log_path(store_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry.rstrip("\n") + "\n")


def delete_consolidation_log(store_dir: Path) -> bool:
    """Delete the store-root ``consolidation-log.md``. Returns whether it existed.

    The caller MUST NOT append a changelog line for this delete — the file being
    removed is the changelog itself."""
    path = consolidation_log_path(store_dir)
    if path.exists():
        path.unlink()
        return True
    return False


def topic_doc_exists(store_dir: Path, slug: str) -> bool:
    """Whether a topic doc already exists for ``slug`` (drives created-vs-updated
    accounting in the organizer)."""
    return topic_path(store_dir, slug).exists()


def _first_line(body: str) -> str:
    for line in body.splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""


def _parse_updated_at(value: object, *, default: datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return default
    return default


# ---------------------------------------------------------------------------
# Superseded-tombstone primitives (reorg data-loss guard)
# ---------------------------------------------------------------------------


def _archive_basename(slug: str, when: datetime) -> str:
    return f"{slug}-{when.strftime('%Y%m%dT%H%M%S')}"


def archive_topic_doc(store_dir: Path, slug: str, *, when: datetime) -> Path | None:
    """Copy the CURRENT ``knowledge/<slug>.md`` to a recoverable
    ``superseded/<slug>-<ts>.md`` tombstone, leaving the original in place.

    Reads the bytes on disk (so a human edit is captured). Returns the archive
    path, or ``None`` if no such topic doc exists. A name collision (same slug+ts
    within one run) gets a ``-2``/``-3``/… suffix so an archive never overwrites
    another."""
    src = topic_path(store_dir, slug)
    try:
        content = src.read_text(encoding="utf-8")
    except OSError:
        return None
    superseded_dir(store_dir).mkdir(parents=True, exist_ok=True)
    base = _archive_basename(slug, when)
    name = base
    i = 2
    while superseded_path(store_dir, name).exists():
        name = f"{base}-{i}"
        i += 1
    dest = superseded_path(store_dir, name)
    atomic_write_text(dest, content)
    return dest


def supersede_topic_doc(store_dir: Path, slug: str, *, when: datetime) -> Path | None:
    """Archive ``knowledge/<slug>.md`` to the tombstone, THEN remove the original
    from the lane. Returns the archive path, or ``None`` if it did not exist
    (never raises). Never a hard delete — the content lives on under ``superseded/``."""
    archived = archive_topic_doc(store_dir, slug, when=when)
    if archived is None:
        return None
    topic_path(store_dir, slug).unlink(missing_ok=True)
    return archived
