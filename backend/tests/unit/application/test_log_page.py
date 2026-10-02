"""``read_log_page`` pages backwards through the daemon log by byte offset.

The properties that matter: a page reads a window near the file's end (never the
whole file), consecutive pages tile the log with no repeat and no gap, a
traceback is never split from the record that raised it, and a cursor stays
valid while the file grows at its end.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from coffer.application import log_page
from coffer.application.log_page import read_log_page

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _line(n: int, level: str = "info", extra: int = 0) -> str:
    return json.dumps(
        {
            "timestamp": (T0 + timedelta(seconds=n)).isoformat().replace("+00:00", "Z"),
            "level": level,
            "logger": "coffer.test",
            "event": f"event-{n}" + "x" * extra,
        }
    )


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _events(page) -> list[str]:
    return [r["event"].split("x")[0] for r in page.records]


def _all(_record) -> bool:
    return True


def test_a_missing_file_is_an_empty_page(tmp_path: Path) -> None:
    page = read_log_page(tmp_path / "nope.log", before=None, limit=10, accept=_all)
    assert page.records == [] and page.next_before is None


def test_pages_tile_the_file_newest_first_without_repeat_or_gap(tmp_path: Path) -> None:
    path = _write(tmp_path / "d.log", [_line(n, extra=200) for n in range(1000)])
    seen: list[str] = []
    before = None
    pages = 0
    while True:
        page = read_log_page(path, before=before, limit=37, accept=_all)
        seen.extend(_events(page))
        pages += 1
        if page.next_before is None:
            break
        before = page.next_before
    assert seen == [f"event-{n}" for n in reversed(range(1000))]
    assert pages == 28  # ceil(1000 / 37)


def test_a_page_reads_a_window_at_the_end_not_the_whole_file(tmp_path: Path, monkeypatch) -> None:
    path = _write(tmp_path / "d.log", [_line(n, extra=200) for n in range(20_000)])
    assert path.stat().st_size > 4_000_000
    read: list[int] = []
    real = log_page._read

    def spy(p: Path, start: int, end: int) -> bytes:
        read.append(end - start)
        return real(p, start, end)

    monkeypatch.setattr(log_page, "_read", spy)
    page = read_log_page(path, before=None, limit=30, accept=_all)
    assert _events(page)[0] == "event-19999" and len(page.records) == 30
    assert sum(read) <= log_page.FIRST_WINDOW


def test_a_traceback_stays_with_the_record_that_raised_it_across_a_window_edge(
    tmp_path: Path,
) -> None:
    lines: list[str] = []
    for n in range(300):
        lines.append(_line(n, extra=300))
        if n % 10 == 0:
            lines += [
                "Traceback (most recent call last):",
                '  File "x.py", line 1, in <module>',
                "    boom()",
                "ValueError: boom",
            ]
    path = _write(tmp_path / "d.log", lines)
    got: list[dict] = []
    before = None
    while True:
        page = read_log_page(path, before=before, limit=7, accept=_all)
        got.extend(page.records)
        if page.next_before is None:
            break
        before = page.next_before
    assert [r["event"].split("x")[0] for r in got] == [f"event-{n}" for n in reversed(range(300))]
    assert not any("raw" in r for r in got)
    folded = [r for r in got if r.get("continuation")]
    assert len(folded) == 30
    assert all(len(r["continuation"]) == 4 for r in folded)


def test_a_cursor_stays_valid_while_the_file_grows(tmp_path: Path) -> None:
    path = _write(tmp_path / "d.log", [_line(n) for n in range(100)])
    first = read_log_page(path, before=None, limit=10, accept=_all)
    with path.open("a", encoding="utf-8") as fh:
        for n in range(100, 150):
            fh.write(_line(n) + "\n")
    second = read_log_page(path, before=first.next_before, limit=10, accept=_all)
    assert _events(first)[0] == "event-99"
    assert _events(second) == [f"event-{n}" for n in range(89, 79, -1)]


def test_since_ends_the_page_for_good(tmp_path: Path) -> None:
    path = _write(tmp_path / "d.log", [_line(n) for n in range(100)])
    since = (T0 + timedelta(seconds=95)).isoformat().replace("+00:00", "Z")
    page = read_log_page(path, before=None, limit=50, accept=_all, since_iso=since)
    assert _events(page) == [f"event-{n}" for n in range(99, 94, -1)]
    assert page.next_before is None


def test_a_sparse_filter_gives_up_with_a_cursor_instead_of_reading_everything(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path / "d.log", [_line(n, extra=200) for n in range(5000)])

    def only_zero(record) -> bool:
        return record["event"].startswith("event-0x")

    page = read_log_page(path, before=None, limit=5, accept=only_zero, max_scan=300_000)
    assert page.records == [] and page.next_before is not None
    # Continuing from that cursor reaches the match at the very start.
    finish = read_log_page(path, before=page.next_before, limit=5, accept=only_zero)
    assert len(finish.records) == 1 and finish.next_before is None
