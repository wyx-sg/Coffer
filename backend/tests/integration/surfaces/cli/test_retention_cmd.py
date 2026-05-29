"""Integration tests for `coffer retention` CLI subcommands."""

from __future__ import annotations

from typer.testing import CliRunner

from coffer.surfaces.cli.main import app

_runner = CliRunner()


# ---------------------------------------------------------------------------
# retention list
# ---------------------------------------------------------------------------


def test_retention_list_shows_policies(in_proc_daemon):
    result = _runner.invoke(app, ["retention", "list"])
    assert result.exit_code == 0, result.output
    # The in_proc_daemon fixture registers audit_log with 365d default
    assert "audit_log" in result.output


# ---------------------------------------------------------------------------
# retention set
# ---------------------------------------------------------------------------


def test_retention_set_days(in_proc_daemon):
    result = _runner.invoke(app, ["retention", "set", "audit_log", "--days", "90"])
    assert result.exit_code == 0, result.output
    assert "90d" in result.output or "90" in result.output


def test_retention_set_forever(in_proc_daemon):
    result = _runner.invoke(app, ["retention", "set", "audit_log", "--forever"])
    assert result.exit_code == 0, result.output
    assert "forever" in result.output


def test_retention_set_unknown_table(in_proc_daemon):
    result = _runner.invoke(app, ["retention", "set", "nonexistent_table", "--days", "30"])
    assert result.exit_code == 4


def test_retention_set_requires_days_or_forever(in_proc_daemon):
    result = _runner.invoke(app, ["retention", "set", "audit_log"])
    assert result.exit_code != 0


def test_retention_set_days_and_forever_conflict(in_proc_daemon):
    result = _runner.invoke(app, ["retention", "set", "audit_log", "--days", "30", "--forever"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# retention prune-now
# ---------------------------------------------------------------------------


def test_retention_prune_now_all(in_proc_daemon):
    result = _runner.invoke(app, ["retention", "prune-now"])
    assert result.exit_code == 0, result.output
    # Should show pruned tables or "nothing to prune"
    assert "audit_log" in result.output or "nothing" in result.output.lower()


def test_retention_prune_now_specific_table(in_proc_daemon):
    result = _runner.invoke(app, ["retention", "prune-now", "--table", "audit_log"])
    assert result.exit_code == 0, result.output
    assert "audit_log" in result.output or "nothing" in result.output.lower()
