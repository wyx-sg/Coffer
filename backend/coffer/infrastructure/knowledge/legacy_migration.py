"""One-way rewrite of the pre-collection knowledge tree (spec knowledge FR-071).

The layer used to keep ``~/.coffer/knowledge/<scope>/{notes,docs,.raw}/<ULID>.md``
and hold every document's *title* only in the ``documents`` table. Dropping that
table without reading it first would destroy every title, so this module runs
inside the same Alembic upgrade, **before** the drops: it reads the rows, then
rewrites the tree into ``~/.coffer/knowledge/<collection>/<slug>.md`` with the
title in the file name and in the frontmatter.

Scopes land as collections by what their content is about, which is the only
distinction the ADR keeps: ``global`` held Shopee-internal material whose
authorization actually matters, so it becomes ``shopee``; every
``project-<ULID>`` scope held the Coffer project's own notes, so they merge into
``coffer``. A scope the user named themselves already denotes a subject, so it
keeps its own name.

Everything here is guarded and idempotent. A database with no ``documents``
table, a tree already in the new shape, a row whose file vanished, a file with
no row — each is a case this walks past rather than one that fails an upgrade.
"""

from __future__ import annotations

import json
import pathlib
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, inspect, text

from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.frontmatter import (
    render_frontmatter,
    split_frontmatter,
)
from coffer.infrastructure.knowledge.naming import slugify, unique_name

#: The lane directories that held content, and the byte-identical copy lane.
LANE_DIRS = ("docs", "notes")
RAW_DIR = ".raw"

#: Lane -> who the file's author was, when nothing better is recorded.
_LANE_ACTOR = {"docs": "user", "notes": "agent"}
_DEFAULT_ACTOR = "agent"

SHOPEE = "shopee"
COFFER = "coffer"

_READMES = {
    SHOPEE: (
        "# shopee\n\n"
        "Shopee-internal knowledge: the account system's services and data "
        "plane, the platforms around them, and the working context for the "
        "tools that reach them. This is the collection whose authorization "
        "matters — an agent should only see it when the human has said so.\n"
    ),
    COFFER: (
        "# coffer\n\n"
        "The Coffer project's own knowledge: notes an agent wrote while "
        "working on Coffer, and the platform references that work depends on.\n"
    ),
}
_GENERIC_README = "# {name}\n\nKnowledge carried over from the {name!r} scope.\n"


@dataclass
class MigrationReport:
    """What the pass actually did — logged by the caller, asserted by tests."""

    files_moved: int = 0
    raw_dirs_removed: int = 0
    scopes_removed: int = 0
    descriptions_filled: int = 0
    collections: set[str] = field(default_factory=set)

    def __str__(self) -> str:
        collections = ", ".join(sorted(self.collections)) or "none"
        return (
            f"{self.files_moved} file(s) into [{collections}], "
            f"{self.raw_dirs_removed} .raw/ removed, "
            f"{self.scopes_removed} scope dir(s) removed, "
            f"{self.descriptions_filled} description(s) filled in"
        )


def collection_for(scope: str) -> str:
    """Which collection a legacy scope's content belongs in."""
    if scope == "global":
        return SHOPEE
    if scope.startswith("project-"):
        return COFFER
    return slugify(scope)


def _has_table(connection: Connection, name: str) -> bool:
    return name in inspect(connection).get_table_names()


def _iso(value: Any) -> str:
    """An ISO-8601 string for whatever the row or the frontmatter carried."""
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        stamped = value if value.tzinfo else value.replace(tzinfo=UTC)
        return stamped.isoformat()
    return str(value)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _legacy_scopes(root: pathlib.Path) -> list[pathlib.Path]:
    """Top-level directories still in the old shape.

    A directory qualifies only if it carries one of the lane directories, so a
    collection this pass already created is never mistaken for a scope and a
    re-run has nothing left to find.
    """
    if not root.is_dir():
        return []
    scopes = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if any((child / lane).is_dir() for lane in (*LANE_DIRS, RAW_DIR)):
            scopes.append(child)
    return scopes


def _rows(connection: Connection) -> dict[tuple[str, str], dict[str, Any]]:
    """Every ``documents`` row, keyed by ``(scope, file name)``.

    The stored ``path`` is absolute and points at the real home directory, so
    the *name* is what survives a test run under ``COFFER_KNOWLEDGE_ROOT``; the
    scope and the lane come from the row itself.
    """
    if not _has_table(connection, "documents"):
        return {}
    columns = {c["name"] for c in inspect(connection).get_columns("documents")}
    lane = "lane" if "lane" in columns else "'docs' AS lane"
    result = connection.execute(
        text(
            f"SELECT resource_name, {lane}, path, title, description, "
            "metadata, created_at, updated_at FROM documents"
        )
    )
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in result.mappings():
        name = pathlib.PurePosixPath(str(row["path"])).name
        rows[(str(row["resource_name"]), name)] = dict(row)
    return rows


#: How much of a derived description to keep. Long enough to say what a file
#: is, short enough that a catalogue of hundreds still fits in a context window.
_DESCRIPTION_CHARS = 200


def _derive_description(body: str) -> str:
    """The file's first real paragraph, for a document that describes nothing.

    Almost nothing in the pre-migration corpus carried a description — it was
    an optional column almost no writer filled. The new catalogue IS the
    retrieval surface (spec knowledge FR-003), so migrating those files with an
    empty line would hand over a corpus nothing can find its way around. The
    first paragraph under the heading is what a person would have written
    there anyway.
    """
    paragraph: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(("#", ">", "|", "---", "```")):
            continue
        if not stripped:
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    text_ = " ".join(paragraph)
    if len(text_) <= _DESCRIPTION_CHARS:
        return text_
    return text_[:_DESCRIPTION_CHARS].rsplit(" ", 1)[0] + "…"


def _target_frontmatter(
    *,
    path: pathlib.Path,
    lane: str,
    row: dict[str, Any] | None,
    old: dict[str, Any],
    body: str = "",
) -> dict[str, str]:
    """The five keys the new format carries, and nothing else.

    The title is the one field that lives only in the database, so the row wins
    when there is one. Everything else prefers what the file already says: the
    file is the artifact the human keeps, and its own timestamps are the ones
    they have seen.
    """
    title = str((row or {}).get("title") or old.get("title") or path.stem)
    description = str(
        (row or {}).get("description") or old.get("description") or _derive_description(body)
    )
    actor = (
        _as_dict(old.get("metadata")).get("actor")
        or _as_dict((row or {}).get("metadata")).get("actor")
        or _LANE_ACTOR.get(lane, _DEFAULT_ACTOR)
    )
    now = datetime.now(UTC).isoformat()
    created = _iso(old.get("created_at")) or _iso((row or {}).get("created_at")) or now
    updated = _iso(old.get("updated_at")) or _iso((row or {}).get("updated_at")) or created
    return {
        "title": title,
        "description": description,
        "actor": str(actor),
        "created_at": created,
        "updated_at": updated,
    }


def _move_file(
    source: pathlib.Path,
    destination_dir: pathlib.Path,
    frontmatter: dict[str, str],
) -> None:
    _, body = split_frontmatter(source.read_text(encoding="utf-8", errors="replace"))
    destination_dir.mkdir(parents=True, exist_ok=True)
    name = unique_name(destination_dir, slugify(frontmatter["title"]))
    (destination_dir / name).write_text(
        render_frontmatter(dict(frontmatter), body), encoding="utf-8"
    )
    source.unlink()


def _write_readme(collection_dir: pathlib.Path) -> None:
    readme = collection_dir / paths.README_NAME
    if readme.exists():
        return
    name = collection_dir.name
    readme.write_text(_READMES.get(name, _GENERIC_README.format(name=name)), encoding="utf-8")


def _prune(directory: pathlib.Path) -> bool:
    """Remove ``directory`` if nothing is left in it. True when it went."""
    if directory.is_dir() and not any(directory.iterdir()):
        directory.rmdir()
        return True
    return False


def migrate_tree(connection: Connection, report: MigrationReport) -> None:
    """Rewrite every legacy scope directory into its collection."""
    root = paths.knowledge_root()
    rows = _rows(connection)
    for scope_dir in _legacy_scopes(root):
        scope = scope_dir.name
        collection_dir = root / collection_for(scope)
        for lane in LANE_DIRS:
            lane_dir = scope_dir / lane
            if not lane_dir.is_dir():
                continue
            for source in sorted(lane_dir.rglob("*.md")):
                if not source.is_file():
                    continue
                old, body = split_frontmatter(source.read_text(encoding="utf-8", errors="replace"))
                frontmatter = _target_frontmatter(
                    path=source,
                    lane=lane,
                    row=rows.get((scope, source.name)),
                    old=old,
                    body=body,
                )
                _move_file(source, collection_dir, frontmatter)
                report.files_moved += 1
                report.collections.add(collection_dir.name)
            shutil.rmtree(lane_dir, ignore_errors=True)
        raw_dir = scope_dir / RAW_DIR
        if raw_dir.is_dir():
            # Byte-identical copies of the lane files: the provenance lane is
            # removed outright, not carried over.
            shutil.rmtree(raw_dir, ignore_errors=True)
            report.raw_dirs_removed += 1
        if collection_dir.is_dir():
            _write_readme(collection_dir)
            report.collections.add(collection_dir.name)
        if _prune(scope_dir):
            report.scopes_removed += 1


def migrate_resources(connection: Connection, report: MigrationReport) -> None:
    """One ``knowledge`` Resource per collection ON DISK; the scopes' rows go.

    A collection's Resource exists to be authorized and nothing else, so its
    config is empty: every knob the old scope carried (retrieval modes, chunk
    size, source auto-update) describes machinery this change removes.

    The collections are read from the filesystem rather than from what this run
    happened to create. A tree already in the new shape — migrated by an
    earlier run, or restored from a backup — reports no work done, and keying
    the rows off that report would delete the scopes' rows and register nothing
    in their place, leaving every file on disk invisible to every agent.
    """
    if not _has_table(connection, "resources"):
        return
    root = paths.knowledge_root()
    on_disk = {
        d.name
        for d in (root.iterdir() if root.is_dir() else [])
        if d.is_dir() and not d.name.startswith(".")
    }
    collections = set(report.collections) | on_disk
    existing = {
        str(name)
        for (name,) in connection.execute(
            text("SELECT name FROM resources WHERE kind = 'knowledge'")
        )
    }
    now = datetime.now(UTC)
    for collection in sorted(collections):
        if collection in existing:
            continue
        connection.execute(
            text(
                "INSERT INTO resources "
                "(kind, name, description, config_json, enabled, created_at, updated_at) "
                "VALUES ('knowledge', :name, NULL, '{}', 1, :now, :now)"
            ),
            {"name": collection, "now": now},
        )
    connection.execute(
        text(
            "DELETE FROM resources WHERE kind = 'knowledge' "
            "AND (name = 'global' OR name LIKE 'project-%')"
        )
    )


def backfill_descriptions(report: MigrationReport) -> None:
    """Give every file already in the new shape a description if it lacks one.

    Separate from the move because it has to reach files this run did not move:
    a tree migrated by an earlier run carries whatever the old ``documents``
    rows said, and almost none of them said anything. An empty description is
    not a cosmetic gap — the catalogue is the only retrieval surface there is
    (spec knowledge FR-003), so a file that describes nothing is one an agent
    scrolls past. Idempotent: a file that already has one is left alone.
    """
    root = paths.knowledge_root()
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if path.name == "README.md":
            continue
        frontmatter, body = split_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if not frontmatter or str(frontmatter.get("description") or "").strip():
            continue
        derived = _derive_description(body)
        if not derived:
            continue
        frontmatter["description"] = derived
        path.write_text(render_frontmatter(frontmatter, body), encoding="utf-8")
        report.descriptions_filled += 1


def migrate(connection: Connection) -> MigrationReport:
    """Rewrite the tree, then reconcile the Resource rows that name it."""
    report = MigrationReport()
    migrate_tree(connection, report)
    backfill_descriptions(report)
    migrate_resources(connection, report)
    return report
