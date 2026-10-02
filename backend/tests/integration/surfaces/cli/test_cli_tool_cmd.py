"""``coffer cli add|edit|rm|show`` for tools added by hand and the interface
read from their help (spec skill-manager "Declare a command-line tool without
a skill", "Show a command-line tool's full interface")."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli.main import app as cli
from tests.support.cli_requirements import DEMO_HELP, FakeCommand, FakeCommandProbe, FakeHelpRunner

from ._cli_requirements_app import CliDaemon, boot_cli_daemon
from ._real_app import extract_json

runner = CliRunner()


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[CliDaemon]:
    probe = FakeCommandProbe({"demo": FakeCommand("3.0.0"), "jq": FakeCommand("1.7")})
    yield from boot_cli_daemon(
        tmp_path, monkeypatch, probe=probe, help_runner=FakeHelpRunner(dict(DEMO_HELP))
    )


def test_add_edit_and_rm(daemon: CliDaemon) -> None:
    added = runner.invoke(
        cli,
        ["cli", "add", "jq", "--title", "JSON", "--min-version", "1.6", "--json"],
    )
    assert added.exit_code == 0, added.output
    body = extract_json(added.output)
    assert body["added"] is True and body["title"] == "JSON" and body["min_version"] == "1.6"
    table = runner.invoke(cli, ["cli", "list"])
    assert "jq" in table.output and "added by you" in table.output
    again = runner.invoke(cli, ["cli", "add", "jq"])
    assert again.exit_code == 5  # already added
    nothing = runner.invoke(cli, ["cli", "edit", "jq"])
    assert nothing.exit_code == 2
    edited = runner.invoke(cli, ["cli", "edit", "jq", "--title", "", "--json"])
    assert edited.exit_code == 0 and extract_json(edited.output)["title"] is None
    refused = runner.invoke(cli, ["cli", "rm", "jq"], input="n\n")
    assert refused.exit_code == 1
    removed = runner.invoke(cli, ["cli", "rm", "jq", "--yes"])
    assert removed.exit_code == 0 and "removed: jq" in removed.output
    assert runner.invoke(cli, ["cli", "rm", "jq", "--yes"]).exit_code == 4
    assert "No command-line tool yet" in runner.invoke(cli, ["cli", "list"]).output


def test_a_bad_declaration_exits_with_invalid_input(daemon: CliDaemon) -> None:
    result = runner.invoke(cli, ["cli", "add", "jq", "--min-version", "latest"])
    assert result.exit_code == 6, result.output


def test_show_prints_the_interface(daemon: CliDaemon) -> None:
    runner.invoke(cli, ["cli", "add", "demo"])
    shown = runner.invoke(cli, ["cli", "show", "demo"])
    assert shown.exit_code == 0, shown.output
    out = shown.output
    assert "added by you" in out and "usage: demo [OPTIONS] COMMAND [ARGS]..." in out
    assert "init" in out and "Set things up" in out and "-v, --verbose" in out
    sub = runner.invoke(cli, ["cli", "show", "demo", "run"])
    assert "TARGET (required)" in sub.output and "What to run" in sub.output
    missing = runner.invoke(cli, ["cli", "show", "demo", "nope"])
    assert missing.exit_code == 4


def test_show_tree_and_json(daemon: CliDaemon) -> None:
    runner.invoke(cli, ["cli", "add", "demo"])
    tree = runner.invoke(cli, ["cli", "show", "demo", "--tree"])
    assert tree.exit_code == 0, tree.output
    lines = [line for line in tree.output.splitlines() if line.strip().startswith("demo")]
    assert lines == [
        "demo  — A demo tool.",
        "  demo init  — Set things up",
        "  demo run  — Run it",
    ]
    as_json = extract_json(runner.invoke(cli, ["cli", "show", "demo", "--json"]).output)
    assert as_json["interface"]["status"] == "ok"
    assert [n["path"] for n in as_json["interface"]["nodes"]] == [[], ["init"], ["run"]]


def test_refresh_reads_the_help_again(daemon: CliDaemon) -> None:
    runner.invoke(cli, ["cli", "add", "demo"])
    runner.invoke(cli, ["cli", "show", "demo"])
    reads = len(daemon.help_runner.calls)
    runner.invoke(cli, ["cli", "show", "demo"])
    assert len(daemon.help_runner.calls) == reads  # kept
    runner.invoke(cli, ["cli", "show", "demo", "--refresh"])
    assert len(daemon.help_runner.calls) == reads * 2
