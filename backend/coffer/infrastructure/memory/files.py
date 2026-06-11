"""Per-fact markdown file I/O for the memory face (the source of truth).

The ONLY module that reads/writes the per-fact ``<slug>.md`` files, renders the
derived ``MEMORY.md`` index, and scans a store dir for deltas (the lazy
reindex-on-read input). Frontmatter parse/render is delegated to the shared
``infrastructure.knowledge.frontmatter`` (the PyYAML owner).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from coffer.domain.memory.fact import Actor, MemoryFact
from coffer.infrastructure.knowledge.frontmatter import (
    render_frontmatter,
    split_frontmatter,
)
from coffer.infrastructure.knowledge.paths import memory_index_path

#: ``MEMORY.md`` is the regenerated index file; never treated as a fact.
_INDEX_NAME = memory_index_path()


@dataclass(frozen=True)
class FactFile:
    """A per-fact file read from disk: the parsed fact + its on-disk metadata."""

    fact: MemoryFact
    path: Path
    content_sha256: str


@dataclass(frozen=True)
class DirScan:
    """A snapshot of every fact file currently in a store dir, keyed by id."""

    files: dict[str, FactFile]


def fact_body_sha256(body: str) -> str:
    """Hash of the markdown body — the reindex no-op gate for a fact."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def render_fact_markdown(fact: MemoryFact) -> str:
    """Render a fact to its on-disk ``<slug>.md`` form (frontmatter + body)."""
    metadata: dict[str, object] = {"actor": fact.actor}
    if fact.type is not None:
        metadata["type"] = fact.type
    frontmatter: dict[str, object] = {
        "id": fact.id,
        "name": fact.name,
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


def parse_fact_markdown(text: str, *, fallback_id: str, mtime: datetime) -> MemoryFact:
    """Parse a per-fact file's text into a ``MemoryFact``.

    Missing frontmatter keys degrade gracefully so an out-of-band / hand-written
    fact file (e.g. Claude's own) still indexes: ``name`` defaults to the id,
    ``description`` to the first body line, ``actor`` to ``"user"``.
    """
    fm, body = split_frontmatter(text)
    raw_metadata = fm.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    actor_raw = str(metadata.get("actor", "user"))
    actor: Actor = "agent" if actor_raw == "agent" else "user"
    fact_type = metadata.get("type")
    name = str(fm.get("name") or fallback_id)
    description = str(fm.get("description") or _first_line(body))
    created = _parse_dt(fm.get("created_at"), default=mtime)
    updated = _parse_dt(fm.get("updated_at"), default=mtime)
    return MemoryFact(
        id=str(fm.get("id") or fallback_id),
        name=name,
        description=description,
        body=body.strip(),
        actor=actor,
        type=str(fact_type) if fact_type is not None else None,
        origin_session_id=(
            str(fm["origin_session_id"]) if fm.get("origin_session_id") is not None else None
        ),
        created_at=created,
        updated_at=updated,
    )


def write_fact_file(path: Path, fact: MemoryFact) -> str:
    """Write a fact's markdown to ``path``; return the body sha256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_fact_markdown(fact), encoding="utf-8")
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


def scan_store_dir(store_dir: Path) -> DirScan:
    """Read every ``*.md`` fact file in ``store_dir`` (excluding ``MEMORY.md``),
    keyed by fact id."""
    files: dict[str, FactFile] = {}
    if not store_dir.exists():
        return DirScan(files=files)
    for path in sorted(store_dir.glob("*.md")):
        if path.name == _INDEX_NAME:
            continue
        ff = read_fact_file(path)
        files[ff.fact.id] = ff
    return DirScan(files=files)


def regenerate_memory_index(store_dir: Path) -> Path:
    """(Re)write ``MEMORY.md`` from the fact files currently on disk, idempotently.

    Format: ``- [name](file.md) — description``, one line per fact, ordered by
    name. Overwrites any prior content (Claude may rewrite it; we own it).
    Scanning the dir (rather than taking a fact list) keeps the index a true
    derived view of the source-of-truth files — out-of-band fact files appear.
    """
    store_dir.mkdir(parents=True, exist_ok=True)
    index_path = store_dir / _INDEX_NAME
    scan = scan_store_dir(store_dir)
    ordered = sorted(scan.files.values(), key=lambda ff: (ff.fact.name.lower(), ff.fact.id))
    lines = ["# Memory", ""]
    for ff in ordered:
        lines.append(f"- [{ff.fact.name}]({ff.path.name}) — {ff.fact.description}")
    body = "\n".join(lines).rstrip() + "\n"
    index_path.write_text(body, encoding="utf-8")
    return index_path


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
