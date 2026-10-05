"""When a Git-imported skill has an update worth offering (spec skill-manager
"Hand a Git-imported skill's update to an agent")."""

from __future__ import annotations

from coffer.domain.skill.source_status import SourceStatus

PIN = "a" * 40
NEW = "c" * 40


def _status(**kw: object) -> SourceStatus:
    return SourceStatus(skill_uid=1).with_(**kw)


def test_a_moved_ref_with_commits_to_the_folder_is_an_update() -> None:
    assert _status(latest_commit=NEW, commits_ahead=2).update_available(PIN) is True


def test_never_checked_is_no_update() -> None:
    assert _status().update_available(PIN) is False


def test_the_ref_still_at_the_pin_is_no_update() -> None:
    assert _status(latest_commit=PIN, commits_ahead=3).update_available(PIN) is False


def test_commits_that_do_not_touch_the_folder_are_no_update() -> None:
    assert _status(latest_commit=NEW, commits_ahead=0).update_available(PIN) is False


def test_with_returns_a_copy() -> None:
    base = _status()
    changed = base.with_(error="boom")
    assert (base.error, changed.error) == (None, "boom")
