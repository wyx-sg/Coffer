"""Integration tests for `coffer daemon backup` and `coffer daemon rotate-token`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from coffer.surfaces.cli.main import app

_runner = CliRunner()


def _create_db(home: Path) -> Path:
    """Create a minimal coffer.db so the backup endpoint has something to copy."""
    db_path = home / ".coffer" / "coffer.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (x INTEGER);")
    conn.execute("INSERT INTO t VALUES (42);")
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# daemon backup
# ---------------------------------------------------------------------------


def test_daemon_backup_default_path(in_proc_daemon):
    """backup writes to the default backups directory and prints the path."""
    home = in_proc_daemon
    _create_db(home)
    result = _runner.invoke(app, ["daemon", "backup"])
    assert result.exit_code == 0, result.output
    # Output should contain "backup:" and the path
    assert "backup:" in result.output
    assert "bytes" in result.output


def test_daemon_backup_custom_path(in_proc_daemon, tmp_path):
    """backup with --to <path> writes to the specified location."""
    home = in_proc_daemon
    _create_db(home)
    dest = tmp_path / "custom_backup" / "out.bak"
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = _runner.invoke(app, ["daemon", "backup", "--to", str(dest)])
    assert result.exit_code == 0, result.output
    assert str(dest) in result.output


# ---------------------------------------------------------------------------
# daemon rotate-token
# ---------------------------------------------------------------------------


def test_daemon_rotate_token(in_proc_daemon):
    """rotate-token should succeed and print a confirmation message."""
    result = _runner.invoke(app, ["daemon", "rotate-token"])
    assert result.exit_code == 0, result.output
    assert "rotated" in result.output.lower() or "token" in result.output.lower()
