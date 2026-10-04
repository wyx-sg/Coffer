"""``coffer --version`` prints the one package version and exits, without a
daemon — the same line ``coffer-daemon --version`` prints."""

from __future__ import annotations

from importlib.metadata import version

from typer.testing import CliRunner

from coffer.surfaces.cli.main import app


def test_version_flag_prints_the_package_version() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output == f"{version('coffer')}\n"


def test_version_flag_wins_over_a_subcommand() -> None:
    """Eager: it answers before any command runs, so it never needs a daemon."""
    result = CliRunner().invoke(app, ["--version", "daemon", "status"])

    assert result.exit_code == 0
    assert result.output == f"{version('coffer')}\n"
