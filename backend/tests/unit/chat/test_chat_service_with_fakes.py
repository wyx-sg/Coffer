"""Unit tests for ChatService using in-memory fake repos + a fake agent provider."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.chat.service import ChatService
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.errors import AgentConfigRejected, ConversationNotFound, UnknownAgent

from .conftest import (
    FakeAgentProvider,
    FakeConversationRepo,
    make_registry,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_service() -> tuple[ChatService, FakeConversationRepo, FakeAgentProvider]:
    conv_repo = FakeConversationRepo()
    registry, provider = make_registry(adapter=None)
    svc = ChatService(conversations=conv_repo, registry=registry)
    return svc, conv_repo, provider


# ---------------------------------------------------------------------------
# Conversation creation + the agent-provider seam
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_conversation_returns_placeholder_title() -> None:
    svc, _conv_repo, _ = make_service()
    conv = await svc.create_conversation(agent_key="builtin")
    assert conv.title == "New conversation"
    assert conv.agent_key == "builtin"


@pytest.mark.asyncio
async def test_create_conversation_calls_provider_init_conversation() -> None:
    svc, _, provider = make_service()
    conv = await svc.create_conversation(agent_key="builtin", agent_config={"model_id": "m-1"})
    assert provider.init_calls == [(conv.id, {"model_id": "m-1"})]


@pytest.mark.asyncio
async def test_create_conversation_unknown_agent_raises_and_persists_nothing() -> None:
    svc, conv_repo, _ = make_service()
    with pytest.raises(UnknownAgent):
        await svc.create_conversation(agent_key="no-such-agent")
    assert await conv_repo.list() == []


@pytest.mark.asyncio
async def test_create_conversation_rolls_back_when_init_rejects_config() -> None:
    conv_repo = FakeConversationRepo()
    provider = FakeAgentProvider(
        adapter=None,
        init_error=AgentConfigRejected(reason="model_not_found", message="no such model"),
    )
    registry, _ = make_registry(provider=provider)
    svc = ChatService(conversations=conv_repo, registry=registry)

    with pytest.raises(AgentConfigRejected):
        await svc.create_conversation(agent_key="builtin", agent_config={"model_id": "ghost"})

    # The conversation row was rolled back — nothing left half-created.
    assert await conv_repo.list() == []


# ---------------------------------------------------------------------------
# Conversation read / rename / model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_conversation_raises_not_found() -> None:
    svc, _, _ = make_service()
    with pytest.raises(ConversationNotFound):
        await svc.get_conversation("missing-id")


@pytest.mark.asyncio
async def test_the_listing_is_channel_conversations_newest_first() -> None:
    svc, conv_repo, _ = make_service()
    c1 = await svc.create_conversation(agent_key="builtin", channel_uid="ch-1", peer_chat_id="p")
    c2 = await svc.create_conversation(agent_key="builtin", channel_uid="ch-1", peer_chat_id="p")
    unowned = await svc.create_conversation(agent_key="builtin")
    await conv_repo.touch(c1.id, datetime(2030, 1, 2, tzinfo=UTC))
    await conv_repo.touch(c2.id, datetime(2030, 1, 1, tzinfo=UTC))
    page = await svc.page_conversations()
    assert [c.id for c in page.items] == [c1.id, c2.id]
    assert unowned.id not in {c.id for c in page.items}
    assert await svc.count_conversations() == 2


@pytest.mark.asyncio
async def test_the_search_matches_the_title_or_the_directory_not_a_message() -> None:
    svc, _, _ = make_service()
    by_title = await svc.create_conversation(
        agent_key="builtin", channel_uid="ch-1", peer_chat_id="p"
    )
    await svc.rename_conversation(by_title.id, new_title="Deploy Notes")
    by_cwd = await svc.create_conversation(
        agent_key="builtin", channel_uid="ch-1", peer_chat_id="p"
    )
    await svc.set_agent_config(by_cwd.id, AgentConfig(cwd="/work/Deploy-tool"))
    other = await svc.create_conversation(agent_key="builtin", channel_uid="ch-1", peer_chat_id="p")
    await svc.rename_conversation(other.id, new_title="Lunch")

    page = await svc.page_conversations(q="deploy")

    assert {c.id for c in page.items} == {by_title.id, by_cwd.id}
    assert await svc.count_conversations(q="  deploy ") == 2


@pytest.mark.asyncio
async def test_rename_conversation() -> None:
    svc, _, _ = make_service()
    conv = await svc.create_conversation(agent_key="builtin")
    updated = await svc.rename_conversation(conv.id, new_title="My Chat")
    assert updated.title == "My Chat"


@pytest.mark.asyncio
async def test_rename_conversation_not_found() -> None:
    svc, _, _ = make_service()
    with pytest.raises(ConversationNotFound):
        await svc.rename_conversation("bad-id", new_title="Title")


# ---------------------------------------------------------------------------
# Conversation deletion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_conversation_removes_the_row() -> None:
    svc, conv_repo, _ = make_service()
    conv = await svc.create_conversation(agent_key="builtin")
    await svc.delete_conversation(conv.id)

    assert await conv_repo.get(conv.id) is None


@pytest.mark.asyncio
async def test_delete_conversation_calls_provider_on_conversation_deleted() -> None:
    svc, _, provider = make_service()
    conv = await svc.create_conversation(agent_key="builtin")
    await svc.delete_conversation(conv.id)
    assert provider.deleted == [conv.id]


@pytest.mark.asyncio
async def test_delete_conversation_not_found() -> None:
    svc, _, _ = make_service()
    with pytest.raises(ConversationNotFound):
        await svc.delete_conversation("no-such-id")


@pytest.mark.asyncio
async def test_delete_conversation_calls_cancel_fn() -> None:
    svc, _, _ = make_service()
    conv = await svc.create_conversation(agent_key="builtin")
    cancelled: list[str] = []
    await svc.delete_conversation(conv.id, cancel_turn_fn=lambda cid: cancelled.append(cid))
    assert conv.id in cancelled


# ---------------------------------------------------------------------------
# Turn bookkeeping: naming and touching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_first_turn_sets_the_title() -> None:
    svc, conv_repo, _ = make_service()
    conv = await svc.create_conversation(agent_key="builtin")
    await svc.begin_turn(conv.id, text="Tell me about Python")
    updated = await conv_repo.get(conv.id)
    assert updated is not None
    assert updated.title == "Tell me about Python"
    assert updated.updated_at > conv.updated_at


@pytest.mark.acceptance(
    spec="chat",
    scenario="a conversation the owner named keeps its name",
)
@pytest.mark.asyncio
async def test_the_first_turn_keeps_a_title_the_owner_set() -> None:
    """A rename outranks the auto-title: the first message must not undo it."""
    svc, conv_repo, _ = make_service()
    conv = await svc.create_conversation(agent_key="builtin")
    await svc.rename_conversation(conv.id, new_title="Tax questions")
    await svc.begin_turn(conv.id, text="Tell me about Python")
    updated = await conv_repo.get(conv.id)
    assert updated is not None
    assert updated.title == "Tax questions"


@pytest.mark.asyncio
async def test_the_title_is_truncated_at_60_chars() -> None:
    svc, conv_repo, _ = make_service()
    conv = await svc.create_conversation(agent_key="builtin")
    await svc.begin_turn(conv.id, text="A" * 100)
    updated = await conv_repo.get(conv.id)
    assert updated is not None
    assert len(updated.title) == 60


@pytest.mark.asyncio
async def test_a_second_turn_does_not_change_the_title() -> None:
    svc, conv_repo, _ = make_service()
    conv = await svc.create_conversation(agent_key="builtin")
    await svc.begin_turn(conv.id, text="First message")
    await svc.begin_turn(conv.id, text="Second message")
    updated = await conv_repo.get(conv.id)
    assert updated is not None
    assert updated.title == "First message"


@pytest.mark.asyncio
async def test_title_hint_names_the_conversation_instead_of_the_message_text() -> None:
    """A caller that wrapped the human's words says which part they wrote.

    A channel turn's text opens with context blocks (provenance, thread
    history) that are identical on every turn; naming from the raw text gave
    every channel conversation the same name.
    """
    svc, conv_repo, _ = make_service()
    conv = await svc.create_conversation(agent_key="builtin")
    await svc.begin_turn(
        conv.id,
        text="[Message origin]\nplatform: seatalk\n\nwhy is the job stuck?",
        title_hint="why is the job stuck?",
    )
    updated = await conv_repo.get(conv.id)
    assert updated is not None
    assert updated.title == "why is the job stuck?"


@pytest.mark.asyncio
async def test_title_hint_does_not_outrank_a_title_the_owner_set() -> None:
    svc, conv_repo, _ = make_service()
    conv = await svc.create_conversation(agent_key="builtin")
    await svc.rename_conversation(conv.id, new_title="Tax questions")
    await svc.begin_turn(conv.id, text="[Message origin]\n\nhello", title_hint="hello")
    updated = await conv_repo.get(conv.id)
    assert updated is not None
    assert updated.title == "Tax questions"


@pytest.mark.asyncio
async def test_an_empty_title_hint_keeps_the_placeholder_rather_than_boilerplate() -> None:
    """Nothing nameable in the message ⇒ say so, don't name it after a header."""
    svc, conv_repo, _ = make_service()
    conv = await svc.create_conversation(agent_key="builtin")
    await svc.begin_turn(conv.id, text="[Message origin]\nplatform: seatalk", title_hint="")
    updated = await conv_repo.get(conv.id)
    assert updated is not None
    assert updated.title == "New conversation"


@pytest.mark.asyncio
async def test_title_hint_is_truncated_like_any_other_title() -> None:
    svc, conv_repo, _ = make_service()
    conv = await svc.create_conversation(agent_key="builtin")
    await svc.begin_turn(conv.id, text="header\n\n" + "A" * 100, title_hint="A" * 100)
    updated = await conv_repo.get(conv.id)
    assert updated is not None
    assert len(updated.title) == 60


@pytest.mark.asyncio
async def test_begin_turn_on_a_missing_conversation_raises() -> None:
    svc, _, _ = make_service()
    with pytest.raises(ConversationNotFound):
        await svc.begin_turn("no-such-id", text="hi")
