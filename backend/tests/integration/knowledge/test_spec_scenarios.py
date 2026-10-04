"""Knowledge scenarios that need a real database.

Every test pins ``HOME`` and ``COFFER_DB_URL`` under ``tmp_path``. The
knowledge layer resolves its root (``~/.coffer/vault/knowledge``) from
``HOME``.
"""

from __future__ import annotations

import asyncio
import pathlib
import sqlite3
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig

from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.resource import Resource

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
    return tmp_path


def _alembic(db: pathlib.Path) -> AlembicConfig:
    cfg = AlembicConfig(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db}")
    return cfg


def _files(root: pathlib.Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


# ----- constraints ---------------------------------------------------------


class _Registry:
    """Just enough of ``ResourceService`` to register and list collections."""

    def __init__(self) -> None:
        self.rows: list[Resource] = []

    async def register(self, *, kind, name, config, actor, **_):  # type: ignore[no-untyped-def]
        now = datetime.now(tz=UTC)
        row = Resource(
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
    spec="knowledge", scenario="a collection is a resource file and a directory, nothing more"
)
def test_the_layer_adds_no_table_and_writes_only_under_its_root(home: pathlib.Path) -> None:
    db = home / "c.db"
    command.upgrade(_alembic(db), "head")
    with sqlite3.connect(db) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert not [t for t in tables if "knowledge" in t.lower()], tables

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
    # Only the documents.
    assert all(path.startswith(".coffer/vault/knowledge/") for path in written), written
