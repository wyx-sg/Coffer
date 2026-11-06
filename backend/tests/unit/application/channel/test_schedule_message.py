"""What a scheduled run is told (spec channels "Run a scheduled task in a fresh
conversation of its own", "Catch up a missed run once, within its grace")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from coffer.application.channel.schedule.message import run_message

NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)


def test_an_on_time_run_is_the_prompt_alone() -> None:
    text = run_message(prompt="Check the build", due_at=NOW, now=NOW, late=False, manual=False)
    assert text == "Check the build"


def test_a_run_by_hand_is_the_prompt_alone() -> None:
    late = NOW - timedelta(days=2)
    assert run_message(prompt="Check", due_at=late, now=NOW, late=True, manual=True) == "Check"


def test_a_late_run_says_when_it_was_due_and_when_it_runs(monkeypatch: object) -> None:
    text = run_message(
        prompt="Check the build", due_at=NOW - timedelta(hours=2), now=NOW, late=True, manual=False
    )
    first, note = text.split("\n\n", 1)
    assert first == "Check the build"
    assert "running late" in note and "Judge whether the work still makes sense" in note
