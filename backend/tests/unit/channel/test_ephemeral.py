"""Which group answers are the asker's business alone (FR-064)."""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.application.channel.ephemeral import private_send, target_for_command
from coffer.domain.channel.envelopes import EphemeralTarget, InboundMessage


def _message(**overrides: object) -> InboundMessage:
    base: dict[str, object] = {
        "channel": "tg",
        "chat_id": "-100group",
        "sender_display": "Yu",
        "text": "/status",
        "platform_message_id": "9",
        "timestamp": datetime.now(tz=UTC),
        "sender_id": "4242",
        "chat_kind": "group",
        "ephemeral_id": "77",
    }
    base.update(overrides)
    return InboundMessage(**base)  # type: ignore[arg-type]


def test_a_group_status_answers_the_asker_alone() -> None:
    assert target_for_command(_message(), "/status") == EphemeralTarget(
        receiver_id="4242", ephemeral_message_id="77"
    )


def test_a_dm_answer_is_never_private() -> None:
    # There is nobody in a DM to hide the answer from.
    assert target_for_command(_message(chat_kind="direct"), "/status") is None


def test_a_shared_state_command_answers_the_room() -> None:
    # /new and /stop change what everyone in the group is talking to.
    assert target_for_command(_message(text="/new"), "/new") is None
    assert target_for_command(_message(text="/stop"), "/stop") is None


def test_a_command_with_arguments_is_still_matched() -> None:
    assert target_for_command(_message(text="/agent codex"), "/agent codex") is not None


def test_without_an_ephemeral_handle_the_answer_is_said_aloud() -> None:
    # An older Bot API server sends no ephemeral id; answering aloud is the
    # behaviour Coffer already had, not a regression.
    assert target_for_command(_message(ephemeral_id=""), "/status") is None


def test_without_a_sender_id_the_answer_is_said_aloud() -> None:
    # An ephemeral message is addressed to a user, not to a chat.
    assert target_for_command(_message(sender_id=""), "/status") is None


def test_an_unrecognised_command_answers_privately() -> None:
    # "Unknown command /nope" is the least useful thing to broadcast to a room.
    assert target_for_command(_message(text="/nope"), "/nope") is not None


def test_private_send_pins_the_target() -> None:
    captured: list[object] = []

    def send(*_args: object, **kwargs: object) -> None:
        captured.append(kwargs.get("ephemeral"))

    target = EphemeralTarget(receiver_id="1", ephemeral_message_id="2")
    private_send(send, target)("binding", "chat", "text")
    assert captured == [target]


def test_private_send_without_a_target_is_the_original_send() -> None:
    def send() -> None: ...

    assert private_send(send, None) is send
