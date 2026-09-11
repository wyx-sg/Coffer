"""Non-message Telegram updates: what the poll subscribes to, and what a
membership change means (FR-058)."""

from __future__ import annotations

from typing import Any

import pytest

from coffer.domain.channel.envelopes import InboundLifecycle
from coffer.infrastructure.channel.telegram_updates import (
    ALLOWED_UPDATES,
    callback_from_query,
    lifecycle_from_update,
    tap_ack,
)

BOT_ID = 999


def _update(status: str, **member: Any) -> dict[str, Any]:
    return {
        "update_id": 1,
        "my_chat_member": {
            "chat": {"id": -100123, "type": "supergroup"},
            "new_chat_member": {"user": {"id": BOT_ID, "is_bot": True}, "status": status, **member},
        },
    }


def test_membership_updates_are_subscribed() -> None:
    # Telegram withholds my_chat_member unless it is named in allowed_updates.
    assert "my_chat_member" in ALLOWED_UPDATES
    assert "message" in ALLOWED_UPDATES and "callback_query" in ALLOWED_UPDATES


def test_updates_with_no_consequence_are_not_subscribed() -> None:
    # Reactions, boosts, join requests and poll answers cost a round trip each
    # and change nothing here.
    assert not (
        {"message_reaction", "chat_boost", "chat_join_request", "poll_answer"}
        & set(ALLOWED_UPDATES)
    )


@pytest.mark.parametrize("status", ["creator", "administrator", "member"])
def test_a_bot_that_is_still_in_the_chat_is_not_an_event(status: str) -> None:
    # Being added changes nothing until somebody pairs (FR-005), so arrival is
    # deliberately not a lifecycle event.
    assert lifecycle_from_update(_update(status), channel="tg", bot_id=BOT_ID) is None


@pytest.mark.parametrize("status", ["left", "kicked"])
def test_a_removed_or_blocked_bot_is_a_removal(status: str) -> None:
    # The same departure SeaTalk reports directly, normalised onto one envelope.
    assert lifecycle_from_update(_update(status), channel="tg", bot_id=BOT_ID) == (
        InboundLifecycle(channel="tg", chat_id="-100123", kind="removed_from_group")
    )


def test_a_restricted_but_still_joined_bot_is_not_an_event() -> None:
    assert (
        lifecycle_from_update(_update("restricted", is_member=True), channel="tg", bot_id=BOT_ID)
        is None
    )


def test_a_restricted_and_departed_bot_is_a_removal() -> None:
    event = lifecycle_from_update(
        _update("restricted", is_member=False), channel="tg", bot_id=BOT_ID
    )
    assert event is not None and event.kind == "removed_from_group"


def test_an_unknown_status_is_not_actionable() -> None:
    # A status Telegram adds later must not be read as "gone" — dropping a peer
    # binding is destructive, so the unknown case does nothing.
    assert lifecycle_from_update(_update("something_new"), channel="tg", bot_id=BOT_ID) is None


def test_an_update_about_another_user_is_ignored() -> None:
    update = _update("kicked")
    update["my_chat_member"]["new_chat_member"]["user"] = {"id": 1234, "is_bot": False}
    assert lifecycle_from_update(update, channel="tg", bot_id=BOT_ID) is None


@pytest.mark.parametrize(
    "update",
    [
        {"update_id": 1},
        {"update_id": 1, "my_chat_member": "nonsense"},
        {"update_id": 1, "my_chat_member": {"chat": {"id": -1}}},
    ],
)
def test_a_malformed_membership_update_is_ignored(update: dict[str, Any]) -> None:
    assert lifecycle_from_update(update, channel="tg", bot_id=BOT_ID) is None


def test_a_chatless_membership_update_is_ignored() -> None:
    update = _update("kicked")
    update["my_chat_member"]["chat"] = {}
    assert lifecycle_from_update(update, channel="tg", bot_id=BOT_ID) is None


# -- callback taps ------------------------------------------------------------


def test_a_group_card_tap_routes_back_to_the_group_thread() -> None:
    query = {
        "id": "cbq-1",
        "from": {"id": 4242},
        "data": "agent:codex",
        "message": {
            "message_id": 77,
            "chat": {"id": -100123, "type": "supergroup"},
            "message_thread_id": 8,
        },
    }
    tap = callback_from_query(query, channel="tg")
    assert (tap.chat_id, tap.chat_kind, tap.thread_id) == ("-100123", "group", "8")
    assert (tap.sender_id, tap.data, tap.callback_id) == ("4242", "agent:codex", "cbq-1")
    assert tap.platform_message_id == "77"


def test_a_dm_card_tap_routes_direct() -> None:
    query = {"id": "c", "from": {"id": 1}, "data": "model:opus", "message": {"chat": {"id": 555}}}
    assert callback_from_query(query, channel="tg").chat_kind == "direct"


def test_tap_ack_shows_the_chosen_value() -> None:
    assert tap_ack("agent:claude_code") == "✓ claude_code"


def test_tap_ack_falls_back_without_a_value() -> None:
    assert tap_ack("") == "✓"
