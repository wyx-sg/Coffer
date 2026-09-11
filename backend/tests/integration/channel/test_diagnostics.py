"""Channel health: configuration the platform will not honour (FR-060), and
the one-tap pairing link (FR-066)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from coffer.infrastructure.channel.telegram_profile import BotIdentity

from .conftest import ChannelEnv, FakeChannelAdapter, inbound


class _TelegramLike(FakeChannelAdapter):
    """A fake that reports a bot identity the way the Telegram adapter does."""

    def __init__(self, identity: BotIdentity) -> None:
        super().__init__()
        self.identity = identity


async def _running(env: ChannelEnv, adapter: FakeChannelAdapter, **config: object) -> str:
    resource = await env.register_channel(
        "tg", config={"channel_type": "telegram", "bot_token_ref": "channel/tg/bot-token", **config}
    )
    env.bind(resource, adapter)
    # The diagnostic reads the LIVE adapter, so the channel has to look started.
    # Registering it directly keeps the test off the reconciler's timing.
    env.runtime._running[resource.name] = SimpleNamespace(adapter=adapter)
    return resource.name


@pytest.mark.acceptance(
    spec="channels", scenario="privacy mode is reported when it contradicts the configuration"
)
async def test_privacy_mode_is_reported_when_it_contradicts_the_configuration(
    env: ChannelEnv,
) -> None:
    adapter = _TelegramLike(BotIdentity(bot_id=1, username="b", reads_all_group_messages=False))
    name = await _running(env, adapter, require_mention=False)

    status = await env.service.status(name)

    assert [d.code for d in status.diagnostics] == ["telegram_privacy_mode"]
    # A finding the user cannot act on is noise; this one names the fix.
    assert "BotFather" in status.diagnostics[0].message


async def test_privacy_mode_is_not_reported_when_the_bot_only_acts_when_addressed(
    env: ChannelEnv,
) -> None:
    # Privacy mode still delivers @mentions and replies, which is all this
    # configuration needs — nothing is contradicted.
    adapter = _TelegramLike(BotIdentity(bot_id=1, username="b", reads_all_group_messages=False))
    name = await _running(env, adapter, require_mention=True)

    assert (await env.service.status(name)).diagnostics == ()


async def test_a_bot_that_can_read_group_messages_is_healthy(env: ChannelEnv) -> None:
    adapter = _TelegramLike(BotIdentity(bot_id=1, username="b", reads_all_group_messages=True))
    name = await _running(env, adapter, require_mention=False)

    assert (await env.service.status(name)).diagnostics == ()


async def test_an_unknown_privacy_state_is_never_a_finding(env: ChannelEnv) -> None:
    # getMe failed, or an older Bot API server omitted the field. Reporting a
    # problem Coffer cannot actually see would be worse than saying nothing.
    adapter = _TelegramLike(BotIdentity(bot_id=1, username="b"))
    name = await _running(env, adapter, require_mention=False)

    assert (await env.service.status(name)).diagnostics == ()


async def test_a_transport_without_an_identity_reports_nothing(env: ChannelEnv) -> None:
    name = await _running(env, FakeChannelAdapter(), require_mention=False)

    assert (await env.service.status(name)).diagnostics == ()


# -- the pairing link (FR-066) ------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="pairing by link claims the code")
async def test_a_pairing_code_comes_with_a_link_that_carries_it(env: ChannelEnv) -> None:
    adapter = _TelegramLike(BotIdentity(bot_id=1, username="cofferbot"))
    name = await _running(env, adapter)

    code, _expires, pair_url = await env.service.issue_pairing_code(name, actor="test")

    assert pair_url == f"https://t.me/cofferbot?start={code}"
    # Opening the link sends "/start <CODE>", which claims it exactly as typing
    # the code does — same single-use, TTL-bounded gate.
    assert env.pairing.try_claim(name, f"/start {code}") is True


async def test_a_channel_with_no_known_username_still_issues_a_code(env: ChannelEnv) -> None:
    name = await _running(env, FakeChannelAdapter())

    code, _expires, pair_url = await env.service.issue_pairing_code(name, actor="test")

    assert len(code) == 8
    assert pair_url == ""  # the typed code is the only way in


# -- private answers in a group, end to end (FR-064) --------------------------


async def test_a_group_status_answers_the_asker_alone(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel(chat_id="-100group", sender_id="4242")

    await env.processor.on_message(
        inbound(
            "tg",
            "-100group",
            "/status",
            chat_kind="group",
            sender_id="4242",
            ephemeral_id="77",
        )
    )

    assert any("Conversation:" in text for _chat, text in adapter.sent)
    target = adapter.sent_ephemeral[-1]
    assert target is not None
    assert (target.receiver_id, target.ephemeral_message_id) == ("4242", "77")
    assert resource.name == "tg"


async def test_a_dm_status_is_not_marked_private(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel(chat_id="owner", sender_id="4242")

    await env.processor.on_message(inbound("tg", "owner", "/status", sender_id="4242"))

    assert adapter.sent_ephemeral[-1] is None


async def test_a_group_new_still_answers_the_room(env: ChannelEnv) -> None:
    # /new changes what everyone in the group is talking to.
    _resource, adapter = await env.paired_channel(chat_id="-100group", sender_id="4242")

    await env.processor.on_message(
        inbound("tg", "-100group", "/new", chat_kind="group", sender_id="4242", ephemeral_id="77")
    )

    assert adapter.sent_ephemeral[-1] is None


async def test_a_group_selection_card_is_not_delivered_privately(env: ChannelEnv) -> None:
    """FR-064 excludes cards on purpose.

    A card is the one surface that must be REWRITTEN after it is used (FR-018),
    and Telegram rewrites an ephemeral message through a different address space
    (`receiver_user_id` + `ephemeral_message_id`) with an edit it documents as
    not guaranteed to arrive. A card that cannot be reliably rewritten keeps
    offering the option already taken — exactly what FR-018 prevents — so it
    stays an ordinary message even though the command that produced it is
    private.
    """
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_buttons=True))
    await env.pair(resource, "-100group", sender_id="4242")

    await env.processor.on_message(
        inbound("tg", "-100group", "/agent", chat_kind="group", sender_id="4242", ephemeral_id="77")
    )

    assert adapter.cards, "the card path must be the one exercised here"
    # The card is the command's ONLY send, and it went out visible. Asserting
    # the whole list rather than its tail is what makes this fail if the card
    # ever starts carrying an ephemeral target — a tail check would still pass
    # if a visible send were appended after a private one.
    assert adapter.sent_ephemeral == [None]


async def test_a_group_command_falling_back_to_text_is_still_private(
    env: ChannelEnv,
) -> None:
    # The card is the exception, not the command: a transport with no buttons
    # answers /agent in text, and that text is the asker's business.
    _resource, adapter = await env.paired_channel(chat_id="-100group", sender_id="4242")

    await env.processor.on_message(
        inbound("tg", "-100group", "/agent", chat_kind="group", sender_id="4242", ephemeral_id="77")
    )

    assert not adapter.cards  # no button support, so the text path ran
    assert adapter.sent_ephemeral[-1] is not None
