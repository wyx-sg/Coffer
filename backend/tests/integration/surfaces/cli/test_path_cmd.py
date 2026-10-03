"""``coffer path logs`` names the daemon's log files, with no daemon running."""

from __future__ import annotations

import json
import pathlib

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli.main import app as cli_app

_runner = CliRunner()


@pytest.mark.acceptance(spec="daemon", scenario="the command line names the daemon log file")
def test_the_command_line_names_the_daemon_log_file(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relocated = (tmp_path / "logs").resolve()
    monkeypatch.setenv("COFFER_LOG_DIR", str(relocated))
    log = relocated / "daemon.log"

    plain = _runner.invoke(cli_app, ["path", "logs"])
    assert plain.exit_code == 0, plain.output
    assert plain.output.split() == [str(relocated), str(log)]
    as_json = json.loads(_runner.invoke(cli_app, ["path", "logs", "--json"]).output)
    assert as_json == {"logs": str(relocated), "daemon_log": str(log)}
    assert not relocated.exists(), "naming the files creates nothing"


def test_the_other_path_targets_are_gone() -> None:
    for target in ("knowledge", "memory", "skill", "agent", "vault"):
        r = _runner.invoke(cli_app, ["path", target])
        assert r.exit_code == 2, target
