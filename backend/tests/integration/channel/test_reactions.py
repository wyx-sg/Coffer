"""FR-036: capability-gated receipt/completion reaction acks.

A ``supports_reactions`` transport (Telegram) reacts 👀 on the owner's own
inbound message on receipt and ✅ on a clean finish; a transport without
reactions (SeaTalk-like) never reaches the reaction path (its typing signal is
the receipt cue). Every reaction is best-effort — a failed one never breaks the
turn. The chat side is the REAL ChatService + TurnOrchestrator; only the
transport and the agent are fakes.
"""

from __future__ import annotations

import pytest

from coffer.domain.chat.events import TextDelta, TurnDone, TurnError, TurnStarted
from tests.unit.chat.conftest import FakeAgentAdapter

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, wait_until


def _clean_reply(text: str = "done") -> FakeAgentAdapter:
    return FakeAgentAdapter(
        [
            TurnStarted(),
            TextDelta(text=text),
            TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
        ]
    )


async def _reacting_channel(
    env: ChannelEnv, *, set_reaction_fails: bool = False
) -> FakeChannelAdapter:
    """A paired channel whose transport supports reactions (like Telegram)."""
    resource = await env.register_channel()
    adapter = env.bind(
        resource,
        FakeChannelAdapter(supports_reactions=True, set_reaction_fails=set_reaction_fails),
    )
    await env.pair(resource, "owner")
    return adapter


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="receipt and completion are acked with reactions where supported",
)
async def test_reaction_ack_on_receipt_and_completion(env: ChannelEnv) -> None:
    env.provider.adapter = _clean_reply("Hello world")
    adapter = await _reacting_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "hi", platform_message_id="msg-42"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    # Both marks land on the user's own inbound message id, receipt before done.
    await wait_until(lambda: ("owner", "msg-42", "✅") in adapter.reactions)

    assert adapter.reactions == [
        ("owner", "msg-42", "👀"),
        ("owner", "msg-42", "✅"),
    ]


async def test_errored_turn_keeps_only_the_receipt_reaction(env: ChannelEnv) -> None:
    # An errored turn earns the 👀 receipt but no ✅ completion mark.
    env.provider.adapter = FakeAgentAdapter(
        [TurnStarted(), TurnError(code="PROVIDER_TIMEOUT", message="upstream timed out")]
    )
    adapter = await _reacting_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "hi", platform_message_id="msg-7"))
    await wait_until(lambda: any(t.startswith("⚠️") for t in adapter.texts()))

    assert adapter.reactions == [("owner", "msg-7", "👀")]


@pytest.mark.acceptance(
    spec="009-channels", scenario="a transport without reaction support attempts no reaction"
)
async def test_no_reaction_on_a_non_reacting_transport(env: ChannelEnv) -> None:
    # A SeaTalk-like transport: supports typing but not reactions. Its receipt
    # cue is the typing signal, so the reaction path is skipped entirely.
    env.provider.adapter = _clean_reply("42")
    resource = await env.register_channel()
    adapter = env.bind(resource, FakeChannelAdapter(supports_reactions=False, supports_edit=False))
    await env.pair(resource, "owner")

    await env.processor.on_message(inbound("tg", "owner", "meaning?"))
    await wait_until(lambda: "42" in adapter.texts())

    assert adapter.reactions == []
    assert adapter.typing == ["owner"]  # the typing signal still fires


@pytest.mark.acceptance(spec="009-channels", scenario="a failed reaction never breaks the turn")
async def test_failing_reaction_still_delivers_the_reply(env: ChannelEnv) -> None:
    env.provider.adapter = _clean_reply("still here")
    adapter = await _reacting_channel(env, set_reaction_fails=True)

    await env.processor.on_message(inbound("tg", "owner", "hi", platform_message_id="msg-9"))
    await wait_until(lambda: "still here" in adapter.texts())

    # The set_reaction calls were attempted (and raised), yet the reply landed.
    assert ("owner", "still here") in adapter.sent
    assert ("owner", "msg-9", "👀") in adapter.reactions
    # The channel stays live for the next message.
    assert env.processor.binding("tg") is not None
