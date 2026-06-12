"""Integration tests for ConversationRepo and MessageRepo against real SQLite.

Covers:
- conversation create / get / list (newest-first) / rename / delete
- message append / seq / list / delete_by_conversation / sweep_streaming
- content-block JSON round-trips (TextBlock, ToolUseBlock, ToolResultBlock)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.message import (
    Message,
    Role,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from coffer.domain.errors import ConversationNotFound
from coffer.infrastructure.chat.persistence import ConversationRepo, MessageRepo
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
    sm = session_maker(engine)
    return engine, ConversationRepo(sm), MessageRepo(sm)


def _conv(title: str = "Hello", *, offset_secs: int = 0) -> Conversation:
    now = datetime.now(tz=UTC)
    ts = now + timedelta(seconds=offset_secs)
    return Conversation(
        id=uuid.uuid4().hex,
        agent_key="builtin",
        title=title,
        model_id=None,
        created_at=ts,
        updated_at=ts,
    )


def _msg(
    conversation_id: str,
    seq: int = 0,
    role: Role = Role.USER,
    status: str = "complete",
) -> Message:
    now = datetime.now(tz=UTC)
    return Message(
        id=uuid.uuid4().hex,
        conversation_id=conversation_id,
        seq=seq,
        role=role,
        content=[TextBlock(text=f"msg-{seq}")],
        status=status,  # type: ignore[arg-type]
        model_id=None,
        prompt_tokens=None,
        completion_tokens=None,
        created_at=now,
    )


# ---------------------------------------------------------------------------
# Restart durability
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="008-agent-chat", scenario="reply survives a restart")
async def test_conversation_and_messages_survive_a_restart(tmp_path):  # type: ignore[no-untyped-def]
    """A genuine restart: write a conversation + a completed assistant reply,
    dispose the engine (close the DB), then open a brand-new engine on the same
    file and confirm everything is present and unchanged."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'restart.db'}"

    # --- First "process": create schema, write data, then shut down. ---
    engine1 = create_async_engine_with_pragmas(db_url)
    async with engine1.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm1 = session_maker(engine1)
    conv_repo1, msg_repo1 = ConversationRepo(sm1), MessageRepo(sm1)

    conv = _conv("Persisted thread")
    await conv_repo1.create(conv)
    await msg_repo1.append(_msg(conv.id, seq=0, role=Role.USER))
    assistant = Message(
        id=uuid.uuid4().hex,
        conversation_id=conv.id,
        seq=1,
        role=Role.ASSISTANT,
        content=[TextBlock(text="the persisted answer")],
        status="complete",
        model_id="m-1",
        prompt_tokens=11,
        completion_tokens=7,
        created_at=datetime.now(tz=UTC),
    )
    await msg_repo1.append(assistant)
    await engine1.dispose()  # the daemon stops

    # --- Second "process": fresh engine on the same file (a restart). ---
    engine2 = create_async_engine_with_pragmas(db_url)
    sm2 = session_maker(engine2)
    conv_repo2, msg_repo2 = ConversationRepo(sm2), MessageRepo(sm2)
    try:
        reloaded_conv = await conv_repo2.get(conv.id)
        assert reloaded_conv is not None
        assert reloaded_conv.title == "Persisted thread"

        msgs = await msg_repo2.list_by_conversation(conv.id)
        assert [m.seq for m in msgs] == [0, 1]
        reply = msgs[1]
        assert reply.role == Role.ASSISTANT
        assert reply.status == "complete"
        assert reply.prompt_tokens == 11
        assert reply.completion_tokens == 7
        assert isinstance(reply.content[0], TextBlock)
        assert reply.content[0].text == "the persisted answer"
    finally:
        await engine2.dispose()


# ---------------------------------------------------------------------------
# Conversation tests
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="008-agent-chat", scenario="manage conversations")
async def test_create_and_get_conversation(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, _ = await _setup(tmp_path)
    try:
        c = _conv("My first chat")
        created = await conv_repo.create(c)
        assert created.id == c.id
        assert created.title == "My first chat"

        fetched = await conv_repo.get(c.id)
        assert fetched is not None
        assert fetched.id == c.id
        assert fetched.title == "My first chat"
    finally:
        await engine.dispose()


async def test_get_missing_conversation_returns_none(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, _ = await _setup(tmp_path)
    try:
        result = await conv_repo.get("does-not-exist")
        assert result is None
    finally:
        await engine.dispose()


@pytest.mark.acceptance(spec="008-agent-chat", scenario="reply survives a restart")
async def test_list_conversations_newest_first(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, _ = await _setup(tmp_path)
    try:
        c1 = _conv("older", offset_secs=0)
        c2 = _conv("newer", offset_secs=5)
        await conv_repo.create(c1)
        await conv_repo.create(c2)

        convs = await conv_repo.list()
        assert len(convs) == 2
        assert convs[0].title == "newer"
        assert convs[1].title == "older"
    finally:
        await engine.dispose()


async def test_rename_conversation(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, _ = await _setup(tmp_path)
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
    engine, conv_repo, _ = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        new_ts = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        await conv_repo.touch(c.id, new_ts)

        fetched = await conv_repo.get(c.id)
        assert fetched is not None
        assert fetched.updated_at == new_ts
    finally:
        await engine.dispose()


async def test_set_model_conversation(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, _ = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        assert c.model_id is None

        updated = await conv_repo.set_model(c.id, "model-abc")
        assert updated.model_id == "model-abc"

        cleared = await conv_repo.set_model(c.id, None)
        assert cleared.model_id is None
    finally:
        await engine.dispose()


async def test_delete_conversation(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, _ = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        await conv_repo.delete(c.id)

        result = await conv_repo.get(c.id)
        assert result is None
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Message tests
# ---------------------------------------------------------------------------


async def test_append_message(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, msg_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        m = _msg(c.id, seq=0)
        saved = await msg_repo.append(m)
        assert saved.id == m.id
        assert saved.seq == 0
    finally:
        await engine.dispose()


async def test_next_seq(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, msg_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())

        seq0 = await msg_repo.next_seq(c.id)
        assert seq0 == 0

        await msg_repo.append(_msg(c.id, seq=seq0))
        seq1 = await msg_repo.next_seq(c.id)
        assert seq1 == 1
    finally:
        await engine.dispose()


async def test_list_by_conversation(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, msg_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        c2 = await conv_repo.create(_conv("other"))

        for seq in range(3):
            await msg_repo.append(_msg(c.id, seq=seq))
        # message in another conversation — should not appear
        await msg_repo.append(_msg(c2.id, seq=0))

        msgs = await msg_repo.list_by_conversation(c.id)
        assert len(msgs) == 3
        assert [m.seq for m in msgs] == [0, 1, 2]
    finally:
        await engine.dispose()


async def test_delete_by_conversation(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, msg_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        for seq in range(3):
            await msg_repo.append(_msg(c.id, seq=seq))

        await msg_repo.delete_by_conversation(c.id)

        msgs = await msg_repo.list_by_conversation(c.id)
        assert msgs == []
    finally:
        await engine.dispose()


async def test_sweep_streaming(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, msg_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())

        now = datetime.now(tz=UTC)
        streaming_msg = Message(
            id=uuid.uuid4().hex,
            conversation_id=c.id,
            seq=0,
            role=Role.ASSISTANT,
            content=[TextBlock(text="partial")],
            status="streaming",
            model_id=None,
            prompt_tokens=None,
            completion_tokens=None,
            created_at=now,
        )
        complete_msg = Message(
            id=uuid.uuid4().hex,
            conversation_id=c.id,
            seq=1,
            role=Role.ASSISTANT,
            content=[TextBlock(text="done")],
            status="complete",
            model_id=None,
            prompt_tokens=None,
            completion_tokens=None,
            created_at=now,
        )

        await msg_repo.append(streaming_msg)
        await msg_repo.append(complete_msg)

        count = await msg_repo.sweep_streaming()
        assert count == 1

        msgs = await msg_repo.list_by_conversation(c.id)
        statuses = {m.id: m.status for m in msgs}
        assert statuses[streaming_msg.id] == "failed"
        assert statuses[complete_msg.id] == "complete"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Content-block round-trip tests
# ---------------------------------------------------------------------------


async def test_content_block_roundtrip_text(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, msg_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        now = datetime.now(tz=UTC)
        msg = Message(
            id=uuid.uuid4().hex,
            conversation_id=c.id,
            seq=0,
            role=Role.USER,
            content=[TextBlock(text="hello world")],
            status="complete",
            model_id=None,
            prompt_tokens=None,
            completion_tokens=None,
            created_at=now,
        )
        saved = await msg_repo.append(msg)
        assert len(saved.content) == 1
        assert isinstance(saved.content[0], TextBlock)
        assert saved.content[0].text == "hello world"
    finally:
        await engine.dispose()


async def test_content_block_roundtrip_tool_use(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, msg_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        now = datetime.now(tz=UTC)
        tool_block = ToolUseBlock(
            tool_use_id="tu-001",
            tool_name="search",
            tool_input={"query": "cats"},
        )
        msg = Message(
            id=uuid.uuid4().hex,
            conversation_id=c.id,
            seq=0,
            role=Role.ASSISTANT,
            content=[tool_block],
            status="complete",
            model_id=None,
            prompt_tokens=10,
            completion_tokens=5,
            created_at=now,
        )
        saved = await msg_repo.append(msg)
        assert len(saved.content) == 1
        assert isinstance(saved.content[0], ToolUseBlock)
        assert saved.content[0].tool_name == "search"
        assert saved.content[0].tool_input == {"query": "cats"}
    finally:
        await engine.dispose()


async def test_content_block_roundtrip_tool_result(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, msg_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        now = datetime.now(tz=UTC)
        result_block = ToolResultBlock(
            tool_use_id="tu-001",
            tool_name="search",
            output={"results": ["cat 1", "cat 2"]},
            error=None,
        )
        msg = Message(
            id=uuid.uuid4().hex,
            conversation_id=c.id,
            seq=0,
            role=Role.ASSISTANT,
            content=[result_block],
            status="complete",
            model_id=None,
            prompt_tokens=None,
            completion_tokens=None,
            created_at=now,
        )
        saved = await msg_repo.append(msg)
        assert len(saved.content) == 1
        assert isinstance(saved.content[0], ToolResultBlock)
        assert saved.content[0].output == {"results": ["cat 1", "cat 2"]}
        assert saved.content[0].error is None
    finally:
        await engine.dispose()


async def test_content_block_roundtrip_tool_result_error(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, msg_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        now = datetime.now(tz=UTC)
        err_block = ToolResultBlock(
            tool_use_id="tu-002",
            tool_name="calc",
            output=None,
            error="division by zero",
        )
        msg = Message(
            id=uuid.uuid4().hex,
            conversation_id=c.id,
            seq=0,
            role=Role.ASSISTANT,
            content=[err_block],
            status="failed",
            model_id=None,
            prompt_tokens=None,
            completion_tokens=None,
            created_at=now,
        )
        saved = await msg_repo.append(msg)
        assert isinstance(saved.content[0], ToolResultBlock)
        assert saved.content[0].output is None
        assert saved.content[0].error == "division by zero"
    finally:
        await engine.dispose()


async def test_mixed_content_blocks_roundtrip(tmp_path):  # type: ignore[no-untyped-def]
    engine, conv_repo, msg_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        now = datetime.now(tz=UTC)
        blocks = [
            TextBlock(text="let me search"),
            ToolUseBlock(tool_use_id="tu-1", tool_name="web_search", tool_input={"q": "test"}),
        ]
        msg = Message(
            id=uuid.uuid4().hex,
            conversation_id=c.id,
            seq=0,
            role=Role.ASSISTANT,
            content=blocks,
            status="complete",
            model_id=None,
            prompt_tokens=None,
            completion_tokens=None,
            created_at=now,
        )
        saved = await msg_repo.append(msg)
        assert len(saved.content) == 2
        assert isinstance(saved.content[0], TextBlock)
        assert isinstance(saved.content[1], ToolUseBlock)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Domain error boundary tests (hardening)
# ---------------------------------------------------------------------------


async def test_rename_missing_conversation_raises_domain_error(tmp_path):  # type: ignore[no-untyped-def]
    """ConversationRepo.rename on a non-existent id raises ConversationNotFound."""
    engine, conv_repo, _ = await _setup(tmp_path)
    try:
        with pytest.raises(ConversationNotFound) as exc_info:
            await conv_repo.rename("no-such-id", "new title")
        assert exc_info.value.conversation_id == "no-such-id"
    finally:
        await engine.dispose()


async def test_set_model_missing_conversation_raises_domain_error(tmp_path):  # type: ignore[no-untyped-def]
    """ConversationRepo.set_model on a non-existent id raises ConversationNotFound."""
    engine, conv_repo, _ = await _setup(tmp_path)
    try:
        with pytest.raises(ConversationNotFound) as exc_info:
            await conv_repo.set_model("no-such-id", "model-abc")
        assert exc_info.value.conversation_id == "no-such-id"
    finally:
        await engine.dispose()


async def test_next_seq_with_gap_is_correct(tmp_path):  # type: ignore[no-untyped-def]
    """next_seq returns MAX(seq)+1 even when there is a seq gap (not COUNT(*))."""
    engine, conv_repo, msg_repo = await _setup(tmp_path)
    try:
        c = await conv_repo.create(_conv())
        # Manually insert a message at seq=5 to create a gap.
        now = datetime.now(tz=UTC)
        gapped_msg = Message(
            id=uuid.uuid4().hex,
            conversation_id=c.id,
            seq=5,
            role=Role.USER,
            content=[TextBlock(text="gapped")],
            status="complete",
            model_id=None,
            prompt_tokens=None,
            completion_tokens=None,
            created_at=now,
        )
        await msg_repo.append(gapped_msg)
        # COUNT(*) would return 1, but MAX(seq)+1 must return 6.
        next_s = await msg_repo.next_seq(c.id)
        assert next_s == 6
    finally:
        await engine.dispose()
