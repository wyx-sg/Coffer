"""A transport that must shorten a live snapshot keeps its status block whole
and clips the answer under it — the header never scrolls away on a long reply."""

from __future__ import annotations

from coffer.infrastructure.channel.seatalk_stream_text import interim_snapshot
from coffer.infrastructure.channel.telegram_draft import clip_draft

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
