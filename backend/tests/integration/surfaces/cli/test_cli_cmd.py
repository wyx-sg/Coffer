"""``coffer cli list|show|check|prompt`` over the real app, with the probe
faked at the composition root (spec skill-manager "Serve required commands on
REST, the command line and the web")."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli.main import app as cli
from tests.support.cli_requirements import FakeCommand, FakeCommandProbe

from ._cli_requirements_app import CliDaemon, boot_cli_daemon
from ._real_app import extract_json

runner = CliRunner()


@pytest.fixture
def probe() -> FakeCommandProbe:
    return FakeCommandProbe(
        {"gh": FakeCommand("2.30.0"), "uv": FakeCommand("0.4.18")},
    )


@pytest.fixture
def daemon(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    probe: FakeCommandProbe,
) -> Iterator[CliDaemon]:
    for d in boot_cli_daemon(tmp_path, monkeypatch, probe=probe):
        d.add_skill("github", '  - command: gh\n    min_version: "2.40"\n')
        d.add_skill("data", "  - jq\n  - uv\n")
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
    assert "outdated" in shown.output and "coffer cli prompt gh" in shown.output
    as_json = runner.invoke(cli, ["cli", "show", "gh", "--json"])
    assert extract_json(as_json.output)["min_version"] == "2.40"
    assert runner.invoke(cli, ["cli", "check"]).exit_code == 0
    one = runner.invoke(cli, ["cli", "check", "uv", "--json"])
    assert extract_json(one.output)["status"] == "ready"
    unknown = runner.invoke(cli, ["cli", "show", "wget"])
    assert unknown.exit_code == 4


@pytest.mark.acceptance(spec="skill-manager", scenario="the command line prints the same prompt")
def test_prompt_prints_the_rest_prompt(daemon: CliDaemon) -> None:
    rest = daemon.client.get("/clis/jq").json()["handoff"]["prompt"]
    printed = runner.invoke(cli, ["cli", "prompt", "jq"])
    assert printed.exit_code == 0, printed.output
    assert printed.output == rest + "\n"
    as_json = extract_json(runner.invoke(cli, ["cli", "prompt", "jq", "--json"]).output)
    assert as_json == {"command": "jq", "handoff": {"prompt": rest}}
    ready = runner.invoke(cli, ["cli", "prompt", "uv"])
    assert ready.exit_code == 5
    assert "nothing to hand off" in ready.output
    assert runner.invoke(cli, ["cli", "prompt", "wget"]).exit_code == 4


def test_install_is_not_a_command(daemon: CliDaemon) -> None:
    result = runner.invoke(cli, ["cli", "install", "jq"])
    assert result.exit_code == 2
