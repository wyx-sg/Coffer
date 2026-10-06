"""The append-only live log a SeaTalk stream shows while a turn runs."""

from __future__ import annotations

import itertools

from coffer.application.channel.turn_log import LOG_HEADER, TurnLog


def test_text_grows_in_paragraphs_split_by_tool_events() -> None:
    log = TurnLog(budget=3000)
    assert log.render() == LOG_HEADER
    log.text("Let me check ")
    log.text("the logs.\n")
    log.boundary()
    log.boundary()
    log.text("\n")  # whitespace alone never opens a paragraph
    log.text("\nThe failure is")
    assert log.render() == f"{LOG_HEADER}\nLet me check the logs.\n\nThe failure is"


def test_every_snapshot_starts_with_the_one_before() -> None:
    log = TurnLog(budget=3000)
    snapshots = [log.render()]
    for i in range(40):
        log.text(f"word{i} ")
        if i % 5 == 4:
            log.boundary()
        snapshots.append(log.render())
    for older, newer in itertools.pairwise(snapshots):
        assert newer.startswith(older)


def test_a_long_log_is_cut_rarely_and_to_half_the_budget() -> None:
    log = TurnLog(budget=400)
    snapshots = []
    for i in range(200):
        log.text(f"第{i}句。\n" if i % 3 == 2 else f"第{i}句 ")
        snapshots.append(log.render())
    assert all(len(s.encode()) <= 400 for s in snapshots)
    cuts = sum(1 for older, newer in itertools.pairwise(snapshots) if not newer.startswith(older))
    assert 0 < cuts <= 12  # 200 sentences, ~10 bytes each, re-cut every ~200 bytes
    assert snapshots[-1].startswith(f"{LOG_HEADER}\n…")
    assert snapshots[-1].endswith("第199句")
