"""Conversation/message repos against real SQLite (spec 008)."""

from __future__ import annotations

import pathlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio

from coffer.domain.chat.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    MessageStatus,
    ToolCall,
)
from coffer.infrastructure.chat.persistence import (
    SqlAlchemyConversationRepo,
    SqlAlchemyMessageRepo,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)


@pytest_asyncio.fixture
async def repos(tmp_path: pathlib.Path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    try:
        yield SqlAlchemyConversationRepo(sm), SqlAlchemyMessageRepo(sm)
    finally:
        await engine.dispose()


def _conv(target_ref: str = "builtin_agent:coffer", when: datetime | None = None) -> Conversation:
    now = when or datetime.now(tz=UTC)
    return Conversation(
        id=uuid.uuid4().hex,
        target_ref=target_ref,
        title=None,
        status=ConversationStatus.ACTIVE,
        model_snapshot={"model": "anthropic:claude-sonnet-4-6"},
        created_at=now,
        updated_at=now,
    )


def _msg(conv_id: str, role: MessageRole, content: str, **kw) -> Message:
    return Message(
        id=uuid.uuid4().hex,
        conversation_id=conv_id,
        role=role,
        content=content,
        status=kw.pop("status", MessageStatus.COMPLETE),
        created_at=datetime.now(tz=UTC),
        **kw,
    )


async def test_create_and_get_conversation(repos):
    conv_repo, _ = repos
    created = await conv_repo.create(_conv())
    fetched = await conv_repo.get(created.id)
    assert fetched is not None
    assert fetched.target_ref == "builtin_agent:coffer"
    assert fetched.model_snapshot == {"model": "anthropic:claude-sonnet-4-6"}
    assert fetched.status is ConversationStatus.ACTIVE


async def test_get_unknown_returns_none(repos):
    conv_repo, _ = repos
    assert await conv_repo.get("nope") is None


async def test_list_orders_newest_first_and_filters_status(repos):
    conv_repo, _ = repos
    base = datetime(2026, 6, 1, tzinfo=UTC)
    older = await conv_repo.create(_conv(when=base))
    newer = await conv_repo.create(_conv(when=base + timedelta(minutes=5)))
    listed = await conv_repo.list()
    assert [c.id for c in listed] == [newer.id, older.id]
    await conv_repo.set_status(older.id, ConversationStatus.ARCHIVED)
    active = await conv_repo.list(status=ConversationStatus.ACTIVE)
    assert [c.id for c in active] == [newer.id]


async def test_messages_persist_in_insertion_order(repos):
    conv_repo, msg_repo = repos
    conv = await conv_repo.create(_conv())
    await msg_repo.add(_msg(conv.id, MessageRole.USER, "hello"))
    await msg_repo.add(_msg(conv.id, MessageRole.ASSISTANT, "hi there"))
    msgs = await msg_repo.list_for(conv.id)
    assert [(m.role, m.content) for m in msgs] == [
        (MessageRole.USER, "hello"),
        (MessageRole.ASSISTANT, "hi there"),
    ]


async def test_tool_calls_roundtrip(repos):
    conv_repo, msg_repo = repos
    conv = await conv_repo.create(_conv())
    tc = ToolCall(
        id="t1", tool="coffer__add_memory", args_summary="{}", result_summary="ok", confirmed=True
    )
    stored = await msg_repo.add(_msg(conv.id, MessageRole.ASSISTANT, "done", tool_calls=[tc]))
    fetched = (await msg_repo.list_for(conv.id))[0]
    assert fetched.id == stored.id
    assert fetched.tool_calls[0].tool == "coffer__add_memory"
    assert fetched.tool_calls[0].confirmed is True


async def test_update_message_status_and_content(repos):
    conv_repo, msg_repo = repos
    conv = await conv_repo.create(_conv())
    m = await msg_repo.add(_msg(conv.id, MessageRole.ASSISTANT, "", status=MessageStatus.STREAMING))
    updated = await msg_repo.update(
        m.id, content="final answer", status=MessageStatus.COMPLETE.value
    )
    assert updated.content == "final answer"
    assert updated.status is MessageStatus.COMPLETE


async def test_set_title(repos):
    conv_repo, _ = repos
    conv = await conv_repo.create(_conv())
    updated = await conv_repo.set_title(conv.id, "Branch naming chat")
    assert updated.title == "Branch naming chat"


async def test_delete_conversation_cascades_messages(repos):
    conv_repo, msg_repo = repos
    conv = await conv_repo.create(_conv())
    await msg_repo.add(_msg(conv.id, MessageRole.USER, "hello"))
    await conv_repo.delete(conv.id)
    assert await conv_repo.get(conv.id) is None
    assert await msg_repo.list_for(conv.id) == []
