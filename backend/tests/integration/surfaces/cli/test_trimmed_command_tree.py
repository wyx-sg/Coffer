"""The shape of the command tree: what each kind's group holds, and what stays a file.

Specs: resource-framework "Offer every management operation on the command
line" and "Locate the log files with coffer path", knowledge "Manage knowledge
in the web UI and on the command line", memory "Manage memory in the web UI and
on the command line", daemon "Change residency from the settings page or the
command line". Everything here runs in process against the Typer app; no daemon is
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


def _walk(cmd: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    yield path, cmd
    for name, sub in (getattr(cmd, "commands", None) or {}).items():
        yield from _walk(sub, (*path, name))


def _tree() -> list[tuple[tuple[str, ...], Any]]:
    return [(p, c) for p, c in _walk(typer.main.get_command(app)) if p]


def _leaves() -> dict[str, Any]:
    return {" ".join(p): c for p, c in _tree() if not getattr(c, "commands", None)}


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


#: Words a command that read, wrote or deleted a plain file's content would use.
_FILE_VERBS = {"read", "write", "edit", "cat", "save", "rm"}


@pytest.mark.acceptance(
    spec="knowledge", scenario="knowledge is managed on the command line, its documents as files"
)
def test_knowledge_is_managed_on_the_command_line_its_documents_as_files() -> None:
    knowledge = {" ".join(p[1:]) for p, _ in _tree() if p[0] == "knowledge" and len(p) > 1}
    assert {
        "collections",
        "create",
        "describe",
        "tree",
        "changes",
        "restore",
        "upload",
    } <= knowledge
    assert not knowledge & _FILE_VERBS
    assert "delete" in knowledge  # a collection's, through the resource framework
    assert _runner.invoke(app, ["path", "knowledge"]).exit_code == 2


@pytest.mark.acceptance(
    spec="memory", scenario="memory is managed on the command line, its notes as files"
)
def test_memory_is_managed_on_the_command_line_its_notes_as_files() -> None:
    memory = {" ".join(p[1:]) for p, _ in _tree() if p[0] == "memory" and len(p) > 1}
    assert {"partitions", "notes", "delivered", "retired", "reading", "sync"} <= memory
    assert not memory & _FILE_VERBS
    assert _leaves()["memory hook"].hidden
    assert "hook" not in _runner.invoke(app, ["memory", "--help"]).output
    assert _runner.invoke(app, ["path", "memory"]).exit_code == 2


@pytest.mark.acceptance(
    spec="daemon", scenario="residency is set in Settings or on the command line"
)
def test_residency_is_set_in_settings_or_on_the_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    residency = {" ".join(p) for p, _ in _tree() if p[:2] == ("daemon", "residency")}
    assert residency == {"daemon residency", "daemon residency show", "daemon residency set"}
    # The old service verbs stay gone, and refusing them opens and writes nothing.
    for argv in (["daemon", "service", "install"], ["daemon", "idle"]):
        assert _runner.invoke(app, argv).exit_code == 2, argv
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
