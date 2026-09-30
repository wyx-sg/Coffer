"""``coffer cli list|show|check|install`` over the real app, with the probe
and Homebrew faked at the composition root (spec skill-manager "Cover
required commands on REST, the command line and the web")."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli import cli_cmd
from coffer.surfaces.cli.main import app as cli
from tests.support.cli_requirements import FAKE_BREW, FakeCommand, FakeCommandProbe, FakeInstaller

from ._cli_requirements_app import CliDaemon, boot_cli_daemon
from ._real_app import extract_json

runner = CliRunner()


@pytest.fixture
def probe() -> FakeCommandProbe:
    return FakeCommandProbe(
        {"gh": FakeCommand("2.30.0"), "uv": FakeCommand("0.4.18")},
    )


@pytest.fixture
def installer(probe: FakeCommandProbe) -> FakeInstaller:
    return FakeInstaller(on_run=lambda: probe.commands.__setitem__("jq", FakeCommand("1.7.1")))


@pytest.fixture
def daemon(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    probe: FakeCommandProbe,
    installer: FakeInstaller,
) -> Iterator[CliDaemon]:
    monkeypatch.setattr(cli_cmd, "POLL_INTERVAL", 0.01)
    for d in boot_cli_daemon(tmp_path, monkeypatch, probe=probe, installer=installer):
        d.add_skill("github", '  - command: gh\n    min_version: "2.40"\n    brew: gh\n')
        d.add_skill("data", "  - command: jq\n    brew: jq\n  - uv\n")
        yield d


@pytest.mark.acceptance(
    spec="skill-manager", scenario="the command line lists required commands problems first"
)
def test_list_json_problems_first(daemon: CliDaemon) -> None:
    result = runner.invoke(cli, ["cli", "list", "--json"])
    assert result.exit_code == 0, result.output
    items = extract_json(result.output)["items"]
    assert [(i["command"], i["status"]) for i in items] == [
        ("jq", "missing"),
        ("gh", "outdated"),
        ("uv", "ready"),
    ]
    assert [n["skill_name"] for n in items[1]["needed_by"]] == ["github"]
    table = runner.invoke(cli, ["cli", "list"])
    assert table.exit_code == 0 and "jq" in table.output


def test_show_and_check(daemon: CliDaemon) -> None:
    shown = runner.invoke(cli, ["cli", "show", "gh"])
    assert shown.exit_code == 0, shown.output
    assert "outdated" in shown.output and "brew upgrade gh" in shown.output
    as_json = runner.invoke(cli, ["cli", "show", "gh", "--json"])
    assert extract_json(as_json.output)["min_version"] == "2.40"
    assert runner.invoke(cli, ["cli", "check"]).exit_code == 0
    one = runner.invoke(cli, ["cli", "check", "uv", "--json"])
    assert extract_json(one.output)["status"] == "ready"
    unknown = runner.invoke(cli, ["cli", "show", "wget"])
    assert unknown.exit_code == 4


@pytest.mark.acceptance(spec="skill-manager", scenario="the command line asks before it installs")
def test_install_asks_first(daemon: CliDaemon, installer: FakeInstaller) -> None:
    declined = runner.invoke(cli, ["cli", "install", "jq"], input="n\n")
    assert declined.exit_code != 0
    assert "brew install jq" in declined.output
    assert "Nothing was run." in declined.output
    assert installer.runs == []

    ran = runner.invoke(cli, ["cli", "install", "jq", "--yes"])
    assert ran.exit_code == 0, ran.output
    assert installer.runs == [(FAKE_BREW, "install", "jq")]
    for line in installer.lines:
        assert line in ran.output
    assert extract_json(runner.invoke(cli, ["cli", "show", "jq", "--json"]).output)["status"] == (
        "ready"
    )


def test_install_of_a_ready_command_runs_nothing(
    daemon: CliDaemon, installer: FakeInstaller
) -> None:
    result = runner.invoke(cli, ["cli", "install", "uv", "--yes"])
    assert result.exit_code == 5
    assert installer.runs == []


def test_a_failed_install_exits_non_zero(daemon: CliDaemon, installer: FakeInstaller) -> None:
    installer.exit_code = 1
    installer.on_run = None
    result = runner.invoke(cli, ["cli", "install", "gh", "--yes"])
    assert result.exit_code == 1
    assert installer.runs == [(FAKE_BREW, "upgrade", "gh")]
