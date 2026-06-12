"""Shared fixtures for knowledge-substrate integration tests.

Builds a real SQLite (unified ``documents``/``chunks``/``documents_fts`` via
``create_all`` + the FTS5 DDL hook) and the document repo + keyword index.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import coffer.infrastructure.knowledge  # noqa: F401 — register ORM + FTS5 DDL
from coffer.infrastructure.knowledge.repository import DocumentRepo
from coffer.infrastructure.knowledge.sqlite_index import SqliteKnowledgeIndex
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)


@dataclass
class SubstrateBundle:
    engine: AsyncEngine
    sm: async_sessionmaker  # type: ignore[type-arg]
    repo: DocumentRepo
    db_path: pathlib.Path

    def index(self, kind: str, resource_name: str) -> SqliteKnowledgeIndex:
        return SqliteKnowledgeIndex(self.sm, kind=kind, resource_name=resource_name)


@pytest_asyncio.fixture
async def substrate(tmp_path: pathlib.Path):
    db_path = tmp_path / "c.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    bundle = SubstrateBundle(engine=engine, sm=sm, repo=DocumentRepo(sm), db_path=db_path)
    try:
        yield bundle
    finally:
        await engine.dispose()
