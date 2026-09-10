"""Log-file plumbing: upstream isolation and the prune."""

from __future__ import annotations

import os
import time

import pytest

from coffer.infrastructure.logging.files import (
    log_dir,
    open_upstream_errlog,
    prune_log_dir,
)


@pytest.fixture(autouse=True)
def _log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path))
    return tmp_path


def test_each_upstream_gets_its_own_file(_log_dir) -> None:
    """The point of the change: an upstream's noise must not land in
    daemon.log, where it evicts Coffer's own lines through rotation."""
    a = open_upstream_errlog("jira")
    b = open_upstream_errlog("confluence")
    assert a is not None and b is not None
    try:
        a.write("jira noise\n")
        b.write("confluence noise\n")
    finally:
        a.close()
        b.close()
    assert (_log_dir / "upstream" / "jira.log").read_text() == "jira noise\n"
    assert (_log_dir / "upstream" / "confluence.log").read_text() == "confluence noise\n"


def test_a_server_name_cannot_escape_the_log_directory(_log_dir) -> None:
    handle = open_upstream_errlog("../../etc/passwd")
    assert handle is not None
    handle.close()
    written = list((_log_dir / "upstream").iterdir())
    assert [p.name for p in written] == [".._.._etc_passwd.log"]


def test_an_oversized_upstream_log_is_rolled_aside(_log_dir, monkeypatch) -> None:
    monkeypatch.setattr("coffer.infrastructure.logging.files._UPSTREAM_MAX_BYTES", 10)
    first = open_upstream_errlog("jira")
    assert first is not None
    first.write("x" * 32)
    first.close()

    second = open_upstream_errlog("jira")
    assert second is not None
    second.write("fresh\n")
    second.close()

    assert (_log_dir / "upstream" / "jira.log").read_text() == "fresh\n"
    assert (_log_dir / "upstream" / "jira.log.1").read_text() == "x" * 32


def test_prune_removes_old_shim_logs_and_keeps_recent_ones(_log_dir) -> None:
    old = _log_dir / "shim-123-1.log"
    recent = _log_dir / "shim-456-2.log"
    old.write_text("old")
    recent.write_text("recent")
    stale = time.time() - 30 * 86400
    os.utime(old, (stale, stale))

    assert prune_log_dir(max_age_days=7) == 1
    assert not old.exists()
    assert recent.exists()


def test_prune_never_touches_the_daemons_own_open_log(_log_dir) -> None:
    """`daemon.log` is bounded by its own RotatingFileHandler, which holds an
    open descriptor — deleting it under the handler breaks logging until the
    next restart."""
    for name in ("daemon.log", "daemon.log.1"):
        path = _log_dir / name
        path.write_text("x")
        stale = time.time() - 365 * 86400
        os.utime(path, (stale, stale))

    assert prune_log_dir(max_age_days=7) == 0
    assert (_log_dir / "daemon.log").exists()
    assert (_log_dir / "daemon.log.1").exists()


def test_prune_is_a_no_op_when_the_directory_does_not_exist(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path / "absent"))
    assert prune_log_dir() == 0


def test_log_dir_honours_the_env_override(_log_dir) -> None:
    assert log_dir() == _log_dir
