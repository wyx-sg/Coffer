"""A transport that must shorten a live snapshot keeps its status block whole
and clips the answer under it — the header never scrolls away on a long reply."""

from __future__ import annotations

from coffer.infrastructure.channel.seatalk_stream_text import interim_snapshot
from coffer.infrastructure.channel.telegram_draft import clip_draft
from coffer.infrastructure.channel.telegram_text import clip_snapshot_utf16, utf16_len

_BLOCK = "⏳ Working · 2m 14s · 7 steps\n✅ Read · a.ts"


def test_seatalk_keeps_the_block_and_clips_the_answer() -> None:
    snapshot = f"{_BLOCK}\n─\n" + "answer " * 1000
    out = interim_snapshot(snapshot)
    assert out.startswith("⏳ Working · 2m 14s · 7 steps\n✅ Read · a.ts\n─\n…")
    assert len(out.encode("utf-8")) <= 3700


def test_seatalk_keeps_a_leading_mention_ahead_of_the_block() -> None:
    tag = '<mention-tag target="seatalk://user?id=7"/> '
    out = interim_snapshot(tag + f"{_BLOCK}\n─\n" + "x" * 5000)
    assert out.startswith(tag + "⏳ Working")


def test_the_telegram_draft_keeps_the_block_and_clips_the_answer() -> None:
    out = clip_draft(f"{_BLOCK}\n─\n" + "y" * 5000, 4096)
    assert len(out) == 4096
    assert out.startswith(f"{_BLOCK}\n─\n…")


def test_a_short_draft_is_left_alone() -> None:
    assert clip_draft("⏳ Working · 1s", 4096) == "⏳ Working · 1s"


def test_the_draft_counts_utf16_units_like_the_platform() -> None:
    """An emoji is one code point and two units: clipped by ``len`` an emoji-heavy
    draft would pass at twice the cap and be refused, killing the live surface."""
    out = clip_draft(f"{_BLOCK}\n─\n" + "😀" * 3000, 4096)
    assert utf16_len(out) <= 4096
    assert out.startswith(f"{_BLOCK}\n─\n…")


def test_the_edited_status_message_keeps_its_header_too() -> None:
    out = clip_snapshot_utf16(f"{_BLOCK}\n─\n" + "z" * 9000, 4096)
    assert utf16_len(out) <= 4096
    assert out.startswith(f"{_BLOCK}\n─\n…")
