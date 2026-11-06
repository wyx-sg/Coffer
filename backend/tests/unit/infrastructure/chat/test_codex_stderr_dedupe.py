"""Codex's repeated start-up warnings reach the daemon log once a day."""

from __future__ import annotations

import datetime

from coffer.infrastructure.chat import codex_app_server as cas


def test_a_repeated_stderr_line_is_logged_once_a_day() -> None:
    cas._SEEN_STDERR.clear()
    day = datetime.date(2026, 11, 6)
    first = "\x1b[2m2026-11-06T01:00:00.1Z\x1b[0m ERROR codex_app_server: ignoring 7 settings"
    again = "\x1b[2m2026-11-06T02:30:00.9Z\x1b[0m ERROR codex_app_server: ignoring 7 settings"
    assert cas._first_today(first, day)
    assert not cas._first_today(again, day)
    assert cas._first_today("ERROR something else", day)
    assert cas._first_today(again, day + datetime.timedelta(days=1))
