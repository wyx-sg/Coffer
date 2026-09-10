"""Per-note markdown file I/O for a knowledge scope (the source of truth).

The ONLY module that reads/writes the per-note ``<slug>.md`` files as indexable
entries and scans a scope's ``notes/`` lane for deltas (the lazy
reindex-on-read input). Frontmatter parse/render is delegated to the shared
``infrastructure.knowledge.frontmatter`` (the PyYAML owner).

A write lands directly in ``notes/``: there is no staging area to drain and no
second lane to be promoted into, so the scan is one flat directory. It skips
hidden entries, which is what keeps the ``.history/`` archive from re-entering
the index as a duplicate of the note it supersedes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from coffer.domain.knowledge.entry import Actor, KnowledgeEntry
from coffer.infrastructure.knowledge.frontmatter import (
    render_frontmatter,
    split_frontmatter,
)
from coffer.infrastructure.knowledge.fs import atomic_write_text
from coffer.infrastructure.knowledge.paths import notes_dir


@dataclass(frozen=True)
class FactFile:
    """A per-fact file read from disk: the parsed fact + its on-disk metadata."""

    fact: KnowledgeEntry
    path: Path
    content_sha256: str


@dataclass(frozen=True)
class DirScan:
    """A snapshot of every fact file currently in a store dir, keyed by id."""

    files: dict[str, FactFile]


def fact_body_sha256(body: str) -> str:
    """Hash of the markdown body — the reindex no-op gate for a fact."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def render_fact_markdown(fact: KnowledgeEntry) -> str:
    """Render a fact to its on-disk ``<slug>.md`` form (frontmatter + body)."""
    metadata: dict[str, object] = {"actor": fact.actor}
    frontmatter: dict[str, object] = {
        # ``kind`` heads every memory file's frontmatter for a consistent,
        # human-readable on-disk header across the lanes.
        "kind": "knowledge",
        "id": fact.id,
        "title": fact.title,
        "description": fact.description,
        "metadata": metadata,
        # Timestamps live in the file (the source of truth) — the mtime
        # fallback in ``parse_fact_markdown`` is only for hand-written files.
        "created_at": fact.created_at.isoformat(),
        "updated_at": fact.updated_at.isoformat(),
    }
    if fact.origin_session_id is not None:
        frontmatter["origin_session_id"] = fact.origin_session_id
    return render_frontmatter(frontmatter, fact.body)


def parse_fact_markdown(text: str, *, fallback_id: str, mtime: datetime) -> KnowledgeEntry:
    """Parse a per-fact file's text into a ``KnowledgeEntry``.

    Missing frontmatter keys degrade gracefully so an out-of-band / hand-written
    fact file (e.g. Claude's own) still indexes: ``title`` defaults to the id,
    ``description`` to the first body line, ``actor`` to ``"user"``. The legacy
    ``name`` key is still accepted as an alias for ``title`` (existing stores /
    externally-written files predate the rename).
    """
    fm, body = split_frontmatter(text)
    raw_metadata = fm.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    actor_raw = str(metadata.get("actor", "user"))
    actor: Actor = "agent" if actor_raw == "agent" else "user"
    title = str(fm.get("title") or fm.get("name") or fallback_id)
    description = str(fm.get("description") or _first_line(body))
    created = _parse_dt(fm.get("created_at"), default=mtime)
    updated = _parse_dt(fm.get("updated_at"), default=mtime)
    return KnowledgeEntry(
        id=str(fm.get("id") or fallback_id),
        title=title,
        description=description,
        body=body.strip(),
        actor=actor,
        origin_session_id=(
            str(fm["origin_session_id"]) if fm.get("origin_session_id") is not None else None
        ),
        created_at=created,
        updated_at=updated,
    )


def write_fact_file(path: Path, fact: KnowledgeEntry) -> str:
    """Write a fact's markdown to ``path`` atomically; return the body sha256."""
    atomic_write_text(path, render_fact_markdown(fact))
    return fact_body_sha256(fact.body)


def read_fact_file(path: Path) -> FactFile:
    """Read + parse one fact file."""
    text = path.read_text(encoding="utf-8")
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    fact = parse_fact_markdown(text, fallback_id=path.stem, mtime=mtime)
    _, body = split_frontmatter(text)
    return FactFile(fact=fact, path=path, content_sha256=fact_body_sha256(body.strip()))


def delete_fact_file(path: Path) -> bool:
    """Delete a fact file. Returns whether it existed."""
    if path.exists():
        path.unlink()
        return True
    return False


def _is_hidden(path: Path, root: Path) -> bool:
    """Whether any path component below ``root`` is dot-prefixed.

    ``pathlib`` globs match dot-prefixed names (the shell's do not), so the
    hidden archives have to be filtered here explicitly: without this, every
    ``.history/`` revision would index alongside the note that replaced it, and
    the atomic writer's own temp files would race the scan."""
    return any(part.startswith(".") for part in path.relative_to(root).parts)


def scan_scope_dir(store_dir: Path) -> DirScan:
    """Read every ``*.md`` note in the store's ``notes/`` lane, keyed by fact id.

    Recurses, but never into a hidden directory — the lane itself is flat, and
    the ``.history/`` archive is a sibling of it rather than a child precisely so
    an archived revision is never a second row for the same note. The lane may
    not exist yet (a scope nobody has written to) → an empty scan, never an
    error. Legacy per-item files at the store ROOT are deliberately NOT scanned
    — they are abandoned in place (see ``legacy_root_facts``)."""
    files: dict[str, FactFile] = {}
    lane = notes_dir(store_dir)
    if not lane.exists():
        return DirScan(files=files)
    for path in sorted(lane.rglob("*.md")):
        if _is_hidden(path, lane):
            continue
        ff = read_fact_file(path)
        files[ff.fact.id] = ff
    return DirScan(files=files)


def legacy_root_facts(store_dir: Path) -> list[Path]:
    """Per-item ``*.md`` files left at the store ROOT by pre-lane builds.

    Everything a scope holds now lives in a lane directory, so a loose markdown
    file at the root is stale by definition. They are abandoned in place (not
    read, not deleted) and reported only as an FR-019 log line."""
    if not store_dir.exists():
        return []
    return [p for p in sorted(store_dir.glob("*.md")) if not p.name.startswith(".")]


def _first_line(body: str) -> str:
    for line in body.splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""


def _parse_dt(value: object, *, default: datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return default
    return default
