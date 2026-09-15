"""Startup notice: config dirs left behind by agent types Coffer dropped.

Coffer narrowed its agent types to ``claude_code`` + ``codex``. Migration 0048
deletes the removed types' resource rows, but nothing on disk is touched — the
migration owns the database, not the user's other tools. So the daemon names
the leftover config directories once — the first start after the migration,
recorded by a marker under ``~/.coffer/state/`` — and lets the user decide.

The paths are hard-coded in ``removed_agent_notice`` (the types are gone from
``AgentType``), so this test hard-codes them too rather than importing them.
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from coffer.surfaces.http.removed_agent_notice import (
    NOTICE_MARKER,
    report_removed_agent_leftovers,
)

LEFTOVER_DIRS = (".config/opencode", ".hermes", ".cursor", ".openclaw")


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING
        and r.message == "removed_agent_type.config_dir_left_in_place"
    ]


def test_logs_nothing_when_no_leftover_dir_exists(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A fresh install must keep its startup output clean."""
    monkeypatch.setenv("HOME", str(tmp_path))
    with caplog.at_level(logging.WARNING, logger="coffer.surfaces.http.removed_agent_notice"):
        report_removed_agent_leftovers()
    assert _warnings(caplog) == []


def test_logs_one_warning_per_existing_dir(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Each removed agent's surviving config dir is named exactly once."""
    monkeypatch.setenv("HOME", str(tmp_path))
    for relative in LEFTOVER_DIRS:
        (tmp_path / relative).mkdir(parents=True)

    with caplog.at_level(logging.WARNING, logger="coffer.surfaces.http.removed_agent_notice"):
        report_removed_agent_leftovers()

    records = _warnings(caplog)
    assert len(records) == len(LEFTOVER_DIRS)
    assert {r.agent_type for r in records} == {  # type: ignore[attr-defined]
        "opencode",
        "hermes",
        "cursor",
        "openclaw",
    }
    assert {r.path for r in records} == {  # type: ignore[attr-defined]
        str(tmp_path / relative) for relative in LEFTOVER_DIRS
    }
    # The notice must say the files are left in place, not that Coffer removed them.
    for record in records:
        assert "left as-is" in record.detail  # type: ignore[attr-defined]


def test_logs_only_the_dirs_that_exist(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A partial cleanup is reported partially — no phantom paths."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".cursor").mkdir(parents=True)

    with caplog.at_level(logging.WARNING, logger="coffer.surfaces.http.removed_agent_notice"):
        report_removed_agent_leftovers()

    records = _warnings(caplog)
    assert len(records) == 1
    assert records[0].agent_type == "cursor"  # type: ignore[attr-defined]
    assert records[0].path == str(tmp_path / ".cursor")  # type: ignore[attr-defined]


def test_the_notice_is_given_once_and_leaves_a_marker(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A user who keeps Cursor installed must not be warned on every boot."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".cursor").mkdir(parents=True)

    with caplog.at_level(logging.WARNING, logger="coffer.surfaces.http.removed_agent_notice"):
        report_removed_agent_leftovers()
        report_removed_agent_leftovers()

    assert len(_warnings(caplog)) == 1
    assert (tmp_path / NOTICE_MARKER).is_file()


def test_the_marker_is_written_even_when_nothing_is_left_over(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clean install has been "told" too: a dir appearing later is the
    user installing that tool afresh, not Coffer's leftovers."""
    monkeypatch.setenv("HOME", str(tmp_path))
    report_removed_agent_leftovers()
    assert (tmp_path / NOTICE_MARKER).is_file()


def test_removing_the_marker_replays_the_notice(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir(parents=True)
    report_removed_agent_leftovers()
    (tmp_path / NOTICE_MARKER).unlink()
    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="coffer.surfaces.http.removed_agent_notice"):
        report_removed_agent_leftovers()

    assert [r.agent_type for r in _warnings(caplog)] == ["hermes"]  # type: ignore[attr-defined]
