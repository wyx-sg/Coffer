"""Knowledge scenarios that need a real database or the migration's real tree.

Every test pins ``HOME``, ``COFFER_DB_URL`` and ``COFFER_KNOWLEDGE_ROOT`` under
``tmp_path``: the migrations move and delete files, and an unset knowledge
root falls back to the developer's real ``~/.coffer/knowledge``.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sqlite3
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig

from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.resource import Resource
from coffer.infrastructure.persistence.migrations import knowledge_tree_0101 as tree

_ALEMBIC_INI = (
    pathlib.Path(__file__).resolve().parents[3]
    / "coffer"
    / "infrastructure"
    / "persistence"
    / "migrations"
    / "alembic.ini"
)


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    return tmp_path


def _alembic(db: pathlib.Path) -> AlembicConfig:
    cfg = AlembicConfig(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db}")
    return cfg


def _files(root: pathlib.Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


# ----- migration -----------------------------------------------------------


@pytest.mark.acceptance(spec="knowledge", scenario="reuse the backup on a second run")
def test_an_existing_backup_is_reported_and_left_alone(home: pathlib.Path) -> None:
    root = home / "knowledge"
    topic = root / "shopee" / "topics" / "session.md"
    topic.parent.mkdir(parents=True)
    topic.write_text("topic\n", encoding="utf-8")
    source = root / "shopee" / "sources" / "note.md"
    source.parent.mkdir(parents=True)
    source.write_text("source\n", encoding="utf-8")

    # What an earlier, interrupted run photographed: the tree as it was then.
    backup = home / f"knowledge{tree.BACKUP_SUFFIX}"
    earlier = backup / "shopee" / "topics" / "session.md"
    earlier.parent.mkdir(parents=True)
    earlier.write_text("the original, as first backed up\n", encoding="utf-8")
    before = _files(backup)

    report = tree.migrate()

    assert report.backup == str(backup)
    assert _files(backup) == before
    # The rewrite itself still happened.
    assert not (root / "shopee" / "topics").exists()
    assert not (root / "shopee" / "sources").exists()


@pytest.mark.acceptance(
    spec="knowledge", scenario="a migrated vault curates on the machine that migrated it"
)
def test_upgrading_through_0101_leaves_curation_on_and_owned_here(home: pathlib.Path) -> None:
    db = home / "c.db"
    (home / "daemon-config.json").write_text(json.dumps({"machine_id": "machine-a"}))
    cfg = _alembic(db)
    command.upgrade(cfg, "0084")
    with sqlite3.connect(db) as conn:
        # A vault from before curation: tidy shipped off, and no owner named.
        conn.execute(
            "INSERT INTO internal_engine_config (id, model, updated_at, auto_tidy_enabled) "
            "VALUES (1, NULL, '2026-09-01 00:00:00', 0)"
        )
        conn.commit()

    command.upgrade(cfg, "0101")

    with sqlite3.connect(db) as conn:
        enabled, owner = conn.execute(
            "SELECT auto_curate_enabled, curate_owner_machine_id FROM internal_engine_config"
        ).fetchone()
    assert enabled == 1
    assert owner == "machine-a"


# ----- constraints ---------------------------------------------------------


class _Registry:
    """Just enough of ``ResourceService`` to register and list collections."""

    def __init__(self) -> None:
        self.rows: list[Resource] = []

    async def register(self, *, kind, name, config, actor, **_):  # type: ignore[no-untyped-def]
        now = datetime.now(tz=UTC)
        row = Resource(
            id=len(self.rows) + 1,
            uid=f"uid-{len(self.rows) + 1}",
            kind=kind,
            name=name,
            description=None,
            config=config,
            enabled=True,
            created_at=now,
            updated_at=now,
            scope=None,
        )
        self.rows.append(row)
        return row

    async def list(self, kind=None, enabled=None):  # type: ignore[no-untyped-def]
        return list(self.rows)


class _Audit:
    async def record(self, event_type, **kwargs):  # type: ignore[no-untyped-def]
        return None


@pytest.mark.acceptance(
    spec="knowledge", scenario="a collection is a resources row and a directory, nothing more"
)
def test_the_layer_adds_no_table_and_writes_only_under_its_root(home: pathlib.Path) -> None:
    db = home / "c.db"
    command.upgrade(_alembic(db), "head")
    with sqlite3.connect(db) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert not [t for t in tables if "knowledge" in t.lower()], tables
    assert "resources" in tables

    before = set(_files(home))
    registry = _Registry()
    service = KnowledgeService(resources=registry, audit=_Audit())  # type: ignore[arg-type]

    async def create_and_submit() -> None:
        # Alembic drives its own event loop, so the service runs in a fresh one.
        await service.create_collection("shopee", actor="user", description="Internal systems.")
        await service.submit(
            collection="shopee", title="Gateway", description="d", body="b", actor="user"
        )

    asyncio.run(create_and_submit())

    assert [(r.kind, r.name) for r in registry.rows] == [(KIND_KNOWLEDGE, "shopee")]
    written = set(_files(home)) - before
    assert written
    assert all(path.startswith("knowledge/") for path in written), written
