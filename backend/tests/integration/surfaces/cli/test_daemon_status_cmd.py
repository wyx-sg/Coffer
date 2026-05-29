from typer.testing import CliRunner

from coffer.surfaces.cli.main import app


def test_daemon_status_unreachable_message(tmp_path, monkeypatch):
    """When daemon.json is absent, status should exit with code 3 and a hint."""
    monkeypatch.setenv("HOME", str(tmp_path))
    res = CliRunner().invoke(app, ["daemon", "status"])
    assert res.exit_code == 3
    assert "daemon" in res.stdout.lower() or "daemon" in (res.stderr or "").lower()
