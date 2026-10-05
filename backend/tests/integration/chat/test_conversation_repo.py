"""Integration tests for the SQLite ConversationRepo (the conversation index).

Covers:
- conversation create / get / list (newest-first, channel conversations only) /
  rename / touch / delete
- the agent config (directory, native session id) read back on the row
- the listing's search (title or directory) and its source and agent filters
- the index surviving a restart
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.chat.conversation_repo import Narrowing
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.errors import ConversationNotFound
from coffer.infrastructure.chat.persistence import ConversationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


async def _setup(tmp_path):  # type: ignore[no-untyped-def]
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, ConversationRepo(session_maker(engine))


def _conv(
    title: str = "Hello", *, offset_secs: int = 0, channel_uid: str | None = "ch-1"
) -> Conversation:
    ts = datetime.now(tz=UTC) + timedelta(seconds=offset_secs)
    return Conversation(
        id=uuid.uuid4().hex,
        agent_key="builtin",
        title=title,
        created_at=ts,
        updated_at=ts,
        channel_uid=channel_uid,
        peer_chat_id="peer" if channel_uid else None,
    )


# ---------------------------------------------------------------------------
# Restart durability
# ---------------------------------------------------------------------------


async def test_the_index_survives_a_restart(tmp_path):  # type: ignore[no-untyped-def]
    """A genuine restart: write a conversation and its agent config, dispose the
    engine (close the DB), then open a brand-new engine on the same file."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'restart.db'}"

    engine1 = create_async_engine_with_pragmas(db_url)
    async with engine1.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    repo1 = ConversationRepo(session_maker(engine1))
    conv = _conv("Persisted thread")
    await repo1.create(conv)
    await repo1.set_agent_config(conv.id, AgentConfig(cwd="/work/app", session_id="s-1"))
    await engine1.dispose()  # the daemon stops

    engine2 = create_async_engine_with_pragmas(db_url)
    repo2 = ConversationRepo(session_maker(engine2))
    try:
        reloaded = await repo2.get(conv.id)
        assert reloaded is not None
        assert reloaded.title == "Persisted thread"
        assert (reloaded.channel_uid, reloaded.peer_chat_id) == ("ch-1", "peer")
        assert reloaded.agent_config == AgentConfig(cwd="/work/app", session_id="s-1")
    finally:
        await engine2.dispose()


# ---------------------------------------------------------------------------
# Conversation tests
# ---------------------------------------------------------------------------


async def test_create_and_get_conversation(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo = await _setup(tmp_path)
    try:
        c = _conv("My first chat")
        created = await conv_repo.create(c)
        assert created.id == c.id
        assert created.title == "My first chat"

        fetched = await conv_repo.get(c.id)
        assert fetched is not None
        assert fetched.id == c.id
        assert fetched.title == "My first chat"
        assert fetched.agent_config == AgentConfig()
    finally:
        await engine.dispose()


async def test_get_missing_conversation_returns_none(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo = await _setup(tmp_path)
    try:
        assert await conv_repo.get("does-not-exist") is None
    finally:
        await engine.dispose()


async def test_list_conversations_newest_first(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo = await _setup(tmp_path)
    try:
        await conv_repo.create(_conv("older", offset_secs=0))
        await conv_repo.create(_conv("newer", offset_secs=5))

        convs = await conv_repo.list()
        assert [c.title for c in convs] == ["newer", "older"]
    finally:
        await engine.dispose()


async def test_the_listing_holds_channel_conversations_only(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo = await _setup(tmp_path)
    try:
        await conv_repo.create(_conv("owned"))
        await conv_repo.create(_conv("unowned", channel_uid=None))

        assert [c.title for c in await conv_repo.list()] == ["owned"]
    finally:
        await engine.dispose()


async def test_list_pages_by_keyset_with_the_id_as_tie_break(tmp_path):  # type: ignore[no-untyped-def]
    """The SQL half of the cursor: strictly after ``(updated_at, id)``, newest
    first, two rows sharing a timestamp ordered by id."""
    engine, conv_repo = await _setup(tmp_path)
    try:
        at = datetime(2026, 9, 1, tzinfo=UTC)
        for cid, ts in (("a", at), ("b", at), ("c", at + timedelta(seconds=1))):
            await conv_repo.create(
                Conversation(
                    id=cid,
                    agent_key="builtin",
                    title=cid,
                    created_at=ts,
                    updated_at=ts,
                    channel_uid="ch-1",
                )
            )

        first = await conv_repo.list(limit=2)
        assert [c.id for c in first] == ["c", "b"]
        rest = await conv_repo.list(limit=2, after=(first[-1].updated_at, first[-1].id))
        assert [c.id for c in rest] == ["a"]
    finally:
        await engine.dispose()


async def test_rename_conversation(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv("original"))
        renamed = await conv_repo.rename(c.id, "updated title")
        assert renamed.title == "updated title"

        fetched = await conv_repo.get(c.id)
        assert fetched is not None
        assert fetched.title == "updated title"
    finally:
        await engine.dispose()


async def test_touch_conversation(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        new_ts = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        await conv_repo.touch(c.id, new_ts)

        fetched = await conv_repo.get(c.id)
        assert fetched is not None
        assert fetched.updated_at == new_ts
    finally:
        await engine.dispose()


async def test_delete_conversation(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        await conv_repo.delete(c.id)

        assert await conv_repo.get(c.id) is None
    finally:
        await engine.dispose()


async def test_rename_missing_conversation_raises_domain_error(tmp_path):  # type: ignore[no-untyped-def]
    """ConversationRepo.rename on a non-existent id raises ConversationNotFound."""
    engine, conv_repo = await _setup(tmp_path)
    try:
        with pytest.raises(ConversationNotFound) as exc_info:
            await conv_repo.rename("no-such-id", "new title")
        assert exc_info.value.conversation_id == "no-such-id"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Listing: search over titles and directories, filters, and the total
# ---------------------------------------------------------------------------


async def test_the_listing_search_reads_titles_and_directories(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo = await _setup(tmp_path)
    try:
        by_title = await conv_repo.create(_conv("Deploy plan", offset_secs=0))
        by_cwd = await conv_repo.create(_conv("Untitled", offset_secs=1))
        by_cjk = await conv_repo.create(_conv("Other", offset_secs=2))
        wildcard = await conv_repo.create(_conv("100%_done", offset_secs=3))
        await conv_repo.set_agent_config(by_cwd.id, AgentConfig(cwd="/work/Deploy-tool"))
        await conv_repo.set_agent_config(by_cjk.id, AgentConfig(cwd="/项目/部署"))
        assert by_title.id and wildcard.id

        async def titles(contains: str | None) -> list[str]:
            rows = await conv_repo.list(contains=contains)
            return [c.title for c in rows]

        assert await titles("DEPLOY") == ["Untitled", "Deploy plan"]  # directory OR title
        assert await titles("部署") == ["Other"]
        assert await titles("100%_") == ["100%_done"]  # wildcards are text
        assert await titles("%") == ["100%_done"]
        assert await titles("nothing here") == []
    finally:
        await engine.dispose()


async def test_the_listing_filters_by_source_and_agent_in_sql(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo = await _setup(tmp_path)
    try:
        await conv_repo.create(
            dataclasses.replace(_conv("a", offset_secs=1, channel_uid="ch-a"), agent_key="codex")
        )
        await conv_repo.create(
            dataclasses.replace(
                _conv("b", offset_secs=2, channel_uid="ch-b"), agent_key="claude_code"
            )
        )
        await conv_repo.create(_conv("c", offset_secs=3, channel_uid="ch-b"))

        async def titles(**kw):  # type: ignore[no-untyped-def]
            return sorted(c.title for c in await conv_repo.list(narrow=Narrowing.of(**kw)))

        assert await titles(sources=["ch-a"]) == ["a"]
        assert await titles(sources=["ch-a", "ch-b"]) == ["a", "b", "c"]
        assert await titles(agents=["codex", "claude_code"]) == ["a", "b"]
        assert await titles(sources=["ch-b"], agents=["claude_code"]) == ["b"]
        assert await titles() == ["a", "b", "c"]
    finally:
        await engine.dispose()
