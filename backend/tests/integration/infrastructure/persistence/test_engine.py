import pytest
from sqlalchemy import text

from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas


@pytest.mark.asyncio
async def test_pragmas_applied(tmp_path):
    db = tmp_path / "coffer.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db}")
    async with engine.connect() as conn:
        journal_mode = await conn.scalar(text("PRAGMA journal_mode;"))
        fk = await conn.scalar(text("PRAGMA foreign_keys;"))
    assert journal_mode == "wal"
    assert fk == 1
    await engine.dispose()
