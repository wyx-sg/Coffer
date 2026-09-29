"""Shared fixtures for the usage tests: a temp database with every table, a
record factory, a spool directory writer and the small fakes the services take."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.domain.usage.pricing import ModelPrice
from coffer.domain.usage.records import Outcome, UsageRecord, Wire
from coffer.infrastructure.chat import persistence as _chat_models  # noqa: F401  (conversations)
from coffer.infrastructure.mcp import persistence as _mcp_models  # noqa: F401  (mcp_invocations)
from coffer.infrastructure.persistence import models as _models  # noqa: F401  (core + usage)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
async def sm(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'u.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield session_maker(engine)
    finally:
        await engine.dispose()


def record(n: int = 1, **overrides: Any) -> UsageRecord:
    """A completed Anthropic attempt with known usage; ``n`` varies its ids."""
    base: dict[str, Any] = {
        "dedupe_key": f"req_{n}",
        "attempt_id": f"att_{n}",
        "started_at": NOW,
        "agent_uid": "agent-claude",
        "agent_type": "claude_code",
        "connection_uid": "conn-anthropic",
        "wire": Wire.ANTHROPIC,
        "endpoint": "/v1/messages",
        "model": "claude-sonnet-4-6",
        "stream": True,
        "status": 200,
        "outcome": Outcome.COMPLETED,
        "duration_ms": 1200,
        "usage_known": True,
        "input_tokens": 1000,
        "cache_write_5m_tokens": 0,
        "cache_write_1h_tokens": 0,
        "cache_read_tokens": 2000,
        "output_tokens": 500,
        "reasoning_tokens": 100,
    }
    base.update(overrides)
    return UsageRecord.model_validate(base)


def write_spool(directory: Path, name: str, lines: Iterable[UsageRecord | str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    with path.open("w", encoding="utf-8") as fh:
        for line in lines:
            text = line if isinstance(line, str) else line.model_dump_json()
            fh.write(text + "\n")
    return path


class FakePrices:
    """``ConnectionPriceLookup`` from a ``{(connection, model): price}`` map."""

    def __init__(self, overrides: Mapping[tuple[str, str], ModelPrice] | None = None) -> None:
        self._overrides = dict(overrides or {})

    async def override_price(
        self, connection_uid: str | None, model: str | None
    ) -> ModelPrice | None:
        return self._overrides.get((connection_uid or "", model or ""))


class FakeNames:
    def __init__(self, names: Mapping[str, str] | None = None) -> None:
        self._names = dict(names or {})

    async def names(self, uids: Iterable[str]) -> Mapping[str, str]:
        return {u: self._names[u] for u in uids if u in self._names}


class FakeClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current


def dumps(obj: Any) -> str:
    return json.dumps(obj)
