from typer.testing import CliRunner

from coffer.surfaces.cli import _client as cli_client
from coffer.surfaces.cli.main import app


def test_daemon_status_unreachable_message(tmp_path, monkeypatch):
    """When daemon.json is absent and the auto-spawn fails/times out, status
    should exit with code 3 and a hint about the daemon log.

    ADR-006: client_or_exit() now auto-spawns; we simulate a spawn that never
    produces daemon.json (timeout) to exercise the error path.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    # Prevent a real daemon from starting; simulate spawn failure (no daemon.json).
    monkeypatch.setattr(cli_client, "_spawn_daemon", lambda: None)
    monkeypatch.setattr(cli_client, "_DAEMON_BOOT_TIMEOUT", 0.05)

    res = CliRunner().invoke(app, ["daemon", "status"])
    assert res.exit_code == 3
    assert "daemon" in res.stdout.lower() or "daemon" in (res.stderr or "").lower()
