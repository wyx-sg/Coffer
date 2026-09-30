"""``message_preview`` — the Conversations list's one-line latest message (spec
chat "Show every conversation on the Conversations page")."""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.application.chat.preview import PREVIEW_MAX_CHARS, message_preview
from coffer.domain.chat.message import ContentBlock, Message, Role, TextBlock, ToolUseBlock


def _msg(*content: ContentBlock, role: Role = Role.USER) -> Message:
    return Message(
        id="m",
        conversation_id="c",
        seq=0,
        role=role,
        content=list(content),
        status="complete",
        model_id=None,
        prompt_tokens=None,
        completion_tokens=None,
        created_at=datetime.now(tz=UTC),
    )


def test_text_blocks_are_joined_on_one_line() -> None:
    msg = _msg(
        TextBlock(text="first\nline"), ToolUseBlock("t", "Bash", {}), TextBlock(text="  second ")
    )
    assert message_preview(msg) == "first line second"


def test_an_agent_reply_previews_by_its_last_words() -> None:
    msg = _msg(
        TextBlock(text="Let me look."),
        ToolUseBlock("t", "Grep", {}),
        TextBlock(text="Fixed: it reconnects now."),
        role=Role.ASSISTANT,
    )
    assert message_preview(msg) == "Fixed: it reconnects now."


def test_a_message_without_words_has_no_preview() -> None:
    assert message_preview(_msg(ToolUseBlock("t", "Bash", {}))) is None
    assert message_preview(_msg(TextBlock(text="  \n "))) is None


def test_a_channel_turns_context_blocks_are_left_out() -> None:
    text = (
        "[Message origin]\nplatform: seatalk\nchat: direct (id: 1)"
        "\n\n[Earlier]\na: b\n\nis it green?"
    )
    assert message_preview(_msg(TextBlock(text=text))) == "is it green?"


def test_a_message_that_is_only_a_block_previews_as_itself() -> None:
    assert message_preview(_msg(TextBlock(text="[Forwarded chat record]\na: hi"))) == (
        "[Forwarded chat record] a: hi"
    )


def test_a_long_message_is_clipped_with_an_ellipsis() -> None:
    line = message_preview(_msg(TextBlock(text="word " * 100)))
    assert line is not None
    assert len(line) <= PREVIEW_MAX_CHARS
    assert line.endswith("…")
