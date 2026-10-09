"""``channel_thread_cursors``: per-conversation cursors into platform threads,
and how a pending cursor is handed to the conversation a turn opens."""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.application.channel.store_ports import PENDING_CONVERSATION, ThreadCursor

from .conftest import ChannelEnv

_AT = datetime(2026, 10, 1, tzinfo=UTC)


def _cursor(conversation_id: str, message_id: str, resource_uid: str = "ch") -> ThreadCursor:
    return ThreadCursor(
        resource_uid=resource_uid,
        chat_id="g",
        thread_id="t",
        conversation_id=conversation_id,
        last_message_id=message_id,
        last_message_at=_AT,
        updated_at=_AT,
    )


async def test_a_pending_cursor_becomes_the_opened_conversations(env: ChannelEnv) -> None:
    repo = env.cursors
    await repo.put(_cursor(PENDING_CONVERSATION, "m-1"))

    await repo.claim("ch", "g", "t", "conv-1")

    assert await repo.get("ch", "g", "t", PENDING_CONVERSATION) is None
    claimed = await repo.get("ch", "g", "t", "conv-1")
    assert claimed is not None and claimed.last_message_id == "m-1"
    assert claimed.last_message_at == _AT


async def test_a_conversation_keeps_its_own_cursor_over_a_pending_one(env: ChannelEnv) -> None:
    repo = env.cursors
    await repo.put(_cursor("conv-1", "m-5"))
    await repo.put(_cursor(PENDING_CONVERSATION, "m-1"))

    await repo.claim("ch", "g", "t", "conv-1")
    await repo.claim("ch", "g", "t", "conv-2")  # nothing pending any more: a no-op

    own = await repo.get("ch", "g", "t", "conv-1")
    assert own is not None and own.last_message_id == "m-5"
    assert [c.conversation_id for c in await repo.list_for_thread("ch", "g", "t")] == ["conv-1"]


async def test_put_replaces_and_a_channel_takes_its_cursors_with_it(env: ChannelEnv) -> None:
    repo = env.cursors
    await repo.put(_cursor("conv-1", "m-1"))
    await repo.put(_cursor("conv-1", "m-2"))
    await repo.put(_cursor("conv-1", "m-1", resource_uid="other"))

    replaced = await repo.get("ch", "g", "t", "conv-1")
    assert replaced is not None and replaced.last_message_id == "m-2"
    await repo.delete_for_channel("ch")
    assert await repo.list_for_thread("ch", "g", "t") == []
    assert await repo.get("other", "g", "t", "conv-1") is not None
