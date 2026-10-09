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
from coffer.infrastructure.chat.adapter_support import (
    channel_system_context,
    owner_prompt_context,
)

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
def test_asks_for_outcome_first_details_png_and_coffer_ask() -> None:
    text = channel_system_context(_SEATALK_GROUP_THREAD)

    assert "The first line is the outcome in one sentence" in text
    assert "only what you write after your last tool call is sent" in text
    assert "as a PNG file" in text
    assert "call `coffer__ask`" in text
    assert "NEEDS YOU" not in text
    assert "`MEDIA:/absolute/path`" in text


@pytest.mark.acceptance(
    spec="channels",
    scenario="only a transport that collapses details is asked for a details section",
)
def test_only_a_collapsing_transport_is_asked_for_a_details_section() -> None:
    telegram = ChannelNote(
        platform="Telegram", chat_kind="direct", renders=RICH_RENDER_NOTES, collapses_details=True
    )

    assert "`## Details` heading, which Coffer collapses" in channel_system_context(telegram)
    assert "## Details" not in channel_system_context(_SEATALK_GROUP_THREAD)
    assert "## Details" not in channel_system_context(None)


def test_the_note_stays_short_because_it_rides_on_every_turn() -> None:
    assert len(channel_system_context(_SEATALK_GROUP_THREAD).split()) < 260


def test_an_unresolvable_channel_keeps_the_guidance() -> None:
    text = channel_system_context(None)

    assert text.startswith("You are replying in a chat channel")
    assert "Short never means dropping evidence" in text
    assert "`coffer__ask`" in text


@pytest.mark.acceptance(
    spec="channels", scenario="the owner's prompt follows Coffer's note under its own heading"
)
def test_the_owner_prompt_follows_the_note_under_its_heading() -> None:
    prompt = "Answer in Chinese.\n\nAlways name the ticket number."
    note = ChannelNote(name="tg", platform="Telegram", chat_kind="direct", owner_prompt=prompt)

    text = channel_system_context(note)
    builtin = channel_system_context(
        ChannelNote(name="tg", platform="Telegram", chat_kind="direct")
    )

    # Coffer's note is kept whole and comes first; the owner's text follows it
    # under the heading, exactly as written.
    assert text == f"{builtin}\n\nInstructions from the channel's owner:\n{prompt}"


@pytest.mark.acceptance(spec="channels", scenario="an empty system prompt appends nothing")
@pytest.mark.parametrize("prompt", ["", "   \n\t "])
def test_an_empty_or_blank_owner_prompt_appends_nothing(prompt: str) -> None:
    note = ChannelNote(platform="SeaTalk", chat_kind="group", owner_prompt=prompt)

    text = channel_system_context(note)

    assert "Instructions from the channel's owner" not in text
    assert text == channel_system_context(ChannelNote(platform="SeaTalk", chat_kind="group"))


def test_a_deleted_channel_has_no_owner_prompt() -> None:
    assert owner_prompt_context(None) == ""


@pytest.mark.acceptance(
    spec="channels", scenario="the note names the thread-reading tool where threads can be read"
)
def test_a_platform_that_reads_threads_names_the_tool() -> None:
    reads = ChannelNote(
        name="ops",
        platform="SeaTalk",
        chat_kind="group",
        in_thread=True,
        renders=SEATALK_RENDER_NOTES,
        reads_threads=True,
    )
    text = channel_system_context(reads)

    assert "`coffer__channel_read_thread`" in text
    assert "[Message origin]" in text
    assert "coffer__channel_read_thread" not in channel_system_context(_SEATALK_GROUP_THREAD)
    assert len(text.split()) < 260


def test_the_owner_prompt_stays_last_after_the_thread_tool_line() -> None:
    note = ChannelNote(
        name="ops",
        platform="SeaTalk",
        chat_kind="group",
        in_thread=True,
        reads_threads=True,
        owner_prompt="Name the ticket number first.",
    )

    text = channel_system_context(note)

    assert text.index("coffer__channel_read_thread") < text.index(
        "Instructions from the channel's owner:"
    )
    assert text.endswith("\nName the ticket number first.")
