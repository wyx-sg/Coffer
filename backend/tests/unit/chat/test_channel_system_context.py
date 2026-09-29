"""Unit tests for ``channel_system_context`` — the note that tells a
channel-driven agent where it is and how to shape a reply for it (spec channels
"Tell a channel-driven agent it is on a chat channel").

"Keep replies short" once read as licence to drop evidence: asked over SeaTalk
to investigate a failed login, the agent answered with a prose summary and the
user had to ask a second time for the log lines behind it. Brevity and evidence
must both be in the note.
"""

from __future__ import annotations

import pytest

from coffer.domain.chat.channel_note import ChannelNote
from coffer.infrastructure.channel.seatalk_caps import SEATALK_RENDER_NOTES
from coffer.infrastructure.channel.telegram_caps import RICH_RENDER_NOTES
from coffer.infrastructure.chat.adapter_support import channel_system_context

_SEATALK_GROUP_THREAD = ChannelNote(
    name="ops", platform="SeaTalk", chat_kind="group", in_thread=True, renders=SEATALK_RENDER_NOTES
)


@pytest.mark.acceptance(
    spec="channels",
    scenario="the channel-driven agent is told it is on a chat channel",
)
def test_names_the_platform_and_chat_kind_and_keeps_the_evidence() -> None:
    text = channel_system_context(_SEATALK_GROUP_THREAD)

    assert text.startswith(
        "You are replying in a SeaTalk group thread (the ops channel), most likely"
    )
    assert "do not narrate your steps" in text
    assert "Short never means dropping evidence" in text
    assert "verbatim" in text
    assert "cannot click permission or confirmation dialogs" in text


@pytest.mark.acceptance(
    spec="channels", scenario="the note lists what renders on the platform the turn is on"
)
def test_the_seatalk_note_says_headings_links_and_tables_do_not_render() -> None:
    text = channel_system_context(_SEATALK_GROUP_THREAD)

    assert "It does NOT render headings (they show as bold), links (write the URL itself)" in text
    assert "tables (write one bullet per row)" in text


def test_the_telegram_note_says_its_rich_markdown_renders() -> None:
    note = ChannelNote(
        name="tg", platform="Telegram", chat_kind="direct", renders=RICH_RENDER_NOTES
    )
    text = channel_system_context(note)

    assert text.startswith("You are replying in a Telegram direct chat (the tg channel)")
    assert "tables of up to 20 columns" in text


@pytest.mark.acceptance(spec="channels", scenario="the note asks for the answer's shape")
def test_asks_for_outcome_first_details_png_and_the_needs_you_line() -> None:
    text = channel_system_context(_SEATALK_GROUP_THREAD)

    assert "The first line is the outcome in one sentence" in text
    assert "`## Details`" in text
    assert "as a PNG file" in text
    assert "`NEEDS YOU: <question> (option / option)`" in text
    assert "`MEDIA:/absolute/path`" in text


def test_the_note_stays_short_because_it_rides_on_every_turn() -> None:
    assert len(channel_system_context(_SEATALK_GROUP_THREAD).split()) < 260


def test_an_unresolvable_channel_keeps_the_guidance() -> None:
    text = channel_system_context(None)

    assert text.startswith("You are replying in a chat channel")
    assert "Short never means dropping evidence" in text
    assert "NEEDS YOU:" in text
