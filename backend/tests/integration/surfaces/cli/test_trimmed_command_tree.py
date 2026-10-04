"""The command line holds only what needs it: the scenarios that are about the
shape of the command tree rather than one command's behaviour.

Specs: resource-framework "Keep the command line to what needs it" and "Locate
the log files with coffer path", knowledge "Manage knowledge in the web UI",
memory "Manage memory in the web UI", daemon "Change residency from the settings
page". Everything here runs in process against the Typer app; no daemon is
started and nothing is written outside ``tmp_path``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import typer
from typer.testing import CliRunner

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.main import app

_runner = CliRunner()
_REPO = Path(__file__).resolve().parents[5]

#: Every command the web UI does not replace (spec resource-framework "Keep the
#: command line to what needs it").
_EXPECTED = {
    "memory hook",
    "proxy token",
    "daemon start",
    "daemon stop",
    "daemon restart",
    "daemon status",
    "path logs",
    "path skill-data",
    "config list",
    "config get",
    "config set",
    "config unset",
    "run",
    "secret list",
    "secret set",
    "cli list",
    "log audit",
    "log mcp",
    "log daemon",
    "mcp test",
    "vault problems",
}


def _walk(cmd: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    yield path, cmd
    for name, sub in (getattr(cmd, "commands", None) or {}).items():
        yield from _walk(sub, (*path, name))


def _tree() -> list[tuple[tuple[str, ...], Any]]:
    return [(p, c) for p, c in _walk(typer.main.get_command(app)) if p]


def _leaves() -> dict[str, Any]:
    return {" ".join(p): c for p, c in _tree() if not getattr(c, "commands", None)}


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="the command tree holds only commands the web UI does not replace",
)
def test_the_command_tree_holds_only_commands_the_web_ui_does_not_replace() -> None:
    assert set(_leaves()) == _EXPECTED
    groups = {p[0] for p, _ in _tree() if len(p) > 1}
    # No group exists for a kind the web UI manages.
    for managed in ("knowledge", "skill", "agent", "channel", "provider", "sync", "tool"):
        assert managed not in groups
        assert managed not in {p[0] for p, _ in _tree()}


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a plain file is read with the reader's own tools"
)
def test_a_plain_file_has_no_command_and_logs_and_skill_data_are_the_exceptions() -> None:
    # `path` offers `logs` and `skill-data`; every other file is named by the web UI, the
    # owning spec or a hand-off prompt and read with the reader's own tools.
    assert {" ".join(p) for p, _ in _tree() if p[0] == "path"} == {
        "path",
        "path logs",
        "path skill-data",
    }
    for target in ("knowledge", "memory", "skill", "agent", "vault"):
        assert _runner.invoke(app, ["path", target]).exit_code == 2, target


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="path logs names the log files and refuses other targets",
)
def test_path_logs_names_the_log_files_and_refuses_other_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    logs = (tmp_path / "logs").resolve()
    monkeypatch.setenv("COFFER_LOG_DIR", str(logs))

    plain = _runner.invoke(app, ["path", "logs"])
    assert plain.exit_code == 0, plain.output
    assert plain.output.split() == [str(logs), str(logs / "daemon.log")]
    as_json = json.loads(_runner.invoke(app, ["path", "logs", "--json"]).output)
    assert as_json == {"logs": str(logs), "daemon_log": str(logs / "daemon.log")}

    refused = _runner.invoke(app, ["path", "skill", "some-skill"])
    assert refused.exit_code != 0
    assert not logs.exists(), "naming the files creates and changes nothing"


@pytest.mark.acceptance(
    spec="knowledge", scenario="no knowledge command group or path target exists"
)
def test_no_knowledge_command_group_or_path_target_exists() -> None:
    assert "knowledge" not in {p[0] for p, _ in _tree()}
    assert _runner.invoke(app, ["knowledge"]).exit_code == 2
    assert _runner.invoke(app, ["path", "knowledge"]).exit_code == 2


@pytest.mark.acceptance(
    spec="memory", scenario="memory is managed from the web UI and has no command group"
)
def test_memory_has_only_the_hidden_hook_and_no_path_target() -> None:
    assert {" ".join(p) for p, _ in _tree() if p[0] == "memory"} == {"memory", "memory hook"}
    leaves = _leaves()
    assert leaves["memory hook"].hidden

    # Absent from the help a person reads, and from the reference page.
    root_help = _runner.invoke(app, ["--help"]).output
    assert "memory" not in root_help
    assert "hook" not in root_help
    reference = "\n".join(
        p.read_text(encoding="utf-8")
        for p in [
            _REPO / "docs-site/reference/cli.md",
            *(_REPO / "docs-site/reference/cli").glob("*.md"),
        ]
    )
    assert "memory hook" not in reference
    assert _runner.invoke(app, ["path", "memory"]).exit_code == 2


@pytest.mark.acceptance(spec="daemon", scenario="residency has no command")
def test_residency_has_no_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    daemon_subcommands = {p[1] for p, _ in _tree() if p[0] == "daemon" and len(p) > 1}
    assert daemon_subcommands == {"start", "stop", "restart", "status"}

    for argv in (
        ["daemon", "service", "install"],
        ["daemon", "service", "status"],
        ["daemon", "idle"],
    ):
        result = _runner.invoke(app, argv)
        assert result.exit_code == 2, argv
    # Nothing was opened or written: the throwaway HOME is still empty.
    assert list(tmp_path.iterdir()) == []


def _daemon_answering(status: int, body: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    def fresh() -> tuple[httpx.Client, object]:
        client = httpx.Client(
            base_url="http://daemon.invalid/api/v1", transport=httpx.MockTransport(handler)
        )
        return client, object()

    monkeypatch.setattr(_cli_client, "client_or_exit", fresh)


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a kept command surfaces the daemon's errors"
)
def test_a_kept_command_surfaces_the_daemons_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _daemon_answering(
        409,
        {"error": {"code": "SOMETHING_CONFLICTS", "message": "the store is busy, retry shortly"}},
        monkeypatch,
    )

    plain = _runner.invoke(app, ["secret", "list"])
    assert plain.exit_code == 5  # the conflict exit code
    assert "the store is busy, retry shortly" in plain.output
    assert "Traceback" not in plain.output

    verbose = _runner.invoke(app, ["--verbose", "secret", "list"])
    assert verbose.exit_code == plain.exit_code
    assert "the store is busy, retry shortly" in verbose.output
    assert "Traceback" in verbose.output or "HTTPStatusError" in verbose.output
