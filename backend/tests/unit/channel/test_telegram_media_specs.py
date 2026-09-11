"""Inbound media coverage and the oversize notice (FR-067)."""

from __future__ import annotations

from typing import Any

import pytest

from coffer.infrastructure.channel.telegram_media import _oversized, media_specs
from coffer.infrastructure.channel.telegram_send import routing_params

_TOO_BIG = 25 * 1024 * 1024


def test_plain_text_message_has_no_media() -> None:
    assert media_specs({"text": "hello"}) == []


def test_largest_photo_size_is_taken() -> None:
    message = {"photo": [{"file_id": "small"}, {"file_id": "large"}]}
    assert media_specs(message) == [("large", "image/jpeg", "photo.jpg")]


@pytest.mark.parametrize(
    ("field", "payload", "expected"),
    [
        ("animation", {"file_id": "a1"}, ("a1", "video/mp4", "animation.mp4")),
        ("sticker", {"file_id": "s1"}, ("s1", "image/webp", "sticker.webp")),
        ("video_note", {"file_id": "v1"}, ("v1", "video/mp4", "video_note.mp4")),
        ("voice", {"file_id": "o1"}, ("o1", "audio/ogg", "voice.ogg")),
        (
            "document",
            {"file_id": "d1", "mime_type": "application/pdf", "file_name": "spec.pdf"},
            ("d1", "application/pdf", "spec.pdf"),
        ),
    ],
)
def test_every_media_field_yields_a_spec(
    field: str, payload: dict[str, Any], expected: tuple[str, str, str]
) -> None:
    # A sticker-only or GIF-only message used to reach the agent as an empty turn.
    assert media_specs({field: payload}) == [expected]


def test_animation_and_its_document_twin_download_once() -> None:
    # Telegram sends a GIF as ``animation`` AND a ``document`` with the same
    # file_id; downloading both would attach the same bytes twice.
    message = {"animation": {"file_id": "same"}, "document": {"file_id": "same"}}
    assert [spec[0] for spec in media_specs(message)] == ["same"]


def test_several_attachments_keep_field_order() -> None:
    message = {
        "photo": [{"file_id": "p"}],
        "document": {"file_id": "d"},
        "voice": {"file_id": "o"},
    }
    assert [spec[0] for spec in media_specs(message)] == ["p", "d", "o"]


def test_oversized_file_is_named() -> None:
    message = {"document": {"file_id": "d", "file_name": "dump.sql", "file_size": _TOO_BIG}}
    assert _oversized(message) == ["dump.sql"]


def test_oversized_falls_back_to_a_type_label_without_a_filename() -> None:
    assert _oversized({"video": {"file_id": "v", "file_size": _TOO_BIG}}) == ["video.mp4"]


def test_file_within_the_limit_is_not_flagged() -> None:
    assert _oversized({"document": {"file_id": "d", "file_size": 1024}}) == []


def test_missing_file_size_is_not_flagged() -> None:
    # Size is optional on the payload; an unknown size is attempted, not refused.
    assert _oversized({"document": {"file_id": "d"}}) == []


def test_routing_params_are_empty_for_an_untargeted_send() -> None:
    assert routing_params() == {}


def test_routing_params_carry_thread_and_reply() -> None:
    assert routing_params("42", "77") == {
        "message_thread_id": 42,
        "reply_parameters": {"message_id": 77, "allow_sending_without_reply": True},
    }


def test_reply_survives_a_deleted_target() -> None:
    # Without allow_sending_without_reply a reply whose target vanished mid-turn
    # would fail and lose the whole answer.
    params = routing_params(reply_to_message_id="5")
    assert params["reply_parameters"]["allow_sending_without_reply"] is True


# -- button vocabulary (FR-069) -----------------------------------------------


def test_a_plain_option_is_an_ordinary_button() -> None:
    from coffer.domain.channel.envelopes import ChoiceButton
    from coffer.infrastructure.channel.telegram_media import inline_keyboard

    keyboard = inline_keyboard([ChoiceButton(label="Codex", value="agent:codex")])
    assert keyboard["inline_keyboard"] == [[{"text": "Codex", "callback_data": "agent:codex"}]]


def test_the_option_in_effect_is_disabled_and_marked() -> None:
    from coffer.domain.channel.envelopes import ChoiceButton
    from coffer.infrastructure.channel.telegram_media import inline_keyboard

    keyboard = inline_keyboard(
        [
            ChoiceButton(label="Codex ✓", value="agent:codex", selected=True),
            ChoiceButton(label="Claude", value="agent:claude_code"),
        ]
    )
    chosen, other = keyboard["inline_keyboard"][0][0], keyboard["inline_keyboard"][1][0]
    # The card stops offering what tapping cannot change.
    assert chosen["disabled"] == {} and chosen["style"] == "success"
    assert "disabled" not in other and "style" not in other


def test_one_option_per_row_keeps_a_menu_readable_on_a_phone() -> None:
    from coffer.domain.channel.envelopes import ChoiceButton
    from coffer.infrastructure.channel.telegram_media import inline_keyboard

    keyboard = inline_keyboard([ChoiceButton(label=str(n), value=f"model:{n}") for n in range(3)])
    assert [len(row) for row in keyboard["inline_keyboard"]] == [1, 1, 1]
