"""Integration tests for ``coffer memory ...``.

See spec memory "Cover memory management on REST and the CLI": the lifecycle
verbs (no ``add``), ``sync``, ``distil``, ``context`` and ``delivery on|off``.
Notes, the index and the retirement record are plain files that ``coffer path
memory`` names (test_path_cmd.py), so no command here reads one.

Most commands are thin HTTP shells, tested the same way
``test_knowledge_cmd.py`` tests its own: boot the real app, route
``_cli_client.client_or_exit`` at a ``TestClient`` over it. ``context`` is
different on purpose (see its own docstring in ``memory_cmd.py``) — it never
goes through ``client_or_exit``'s detect-or-spawn, so it is tested by
monkeypatching ``live_daemon``/``httpx.post`` directly, proving the "never
fail a session" contract even when nothing is listening at all.

The fixture repository is a **real** ``git init``, because a partition is keyed
on a repository and a plain directory deliberately earns none ("Identify a partition
by its repository", "Create no partition for a non-repository directory");
and every test that wants notes runs ``sync`` **then** ``distil``, because
aggregation writes only the hidden ``.raw/`` and the notes are the distil pass's
output ("Keep raw entries verbatim and hidden"). With no internal connection
configured that pass is the mechanical one — one note per entry, and an index
over them ("Distil mechanically with no internal connection").
"""

from __future__ import annotations

import json
import pathlib
import shutil
from datetime import UTC
from datetime import datetime as dt

import httpx
import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
import coffer.surfaces.cli.memory_cmd as memory_cmd
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.integration.memory.conftest import claude_code_config, init_repository

_runner = CliRunner()
_TOKEN = "test-token-memory-cli"

_CC_PROJECT_MEMORY = """---
name: python-lockfile
description: Dependencies are locked with uv
metadata:
  type: project
---

Run `uv sync --frozen` in this project; a plain `pip install` drifts.
"""

_CC_PERSONAL_MEMORY = """---
name: worktree-development
description: Always develop in a git worktree
metadata:
  type: user
---

Multiple parallel sessions share the repo — always work in a worktree.
"""


def _extract_json(output: str) -> str:
    lines = output.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line and line[0] in "[{":
            return "".join(lines[i:])
    return output


@pytest.fixture
def memory_cli_daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59900")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59909")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)

    app = create_app()
    set_active_token(_TOKEN)

    info = DaemonInfo(
        version=1,
        pid=12345,
        port=59900,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )

    fake_client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    fake_client.__enter__()

    class _PersistentClient:
        def __init__(self, inner: TestClient) -> None:
            self._inner = inner

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        def __getattr__(self, item):  # type: ignore[no-untyped-def]
            return getattr(self._inner, item)

    monkeypatch.setattr(
        _cli_client, "client_or_exit", lambda: (_PersistentClient(fake_client), info)
    )
    yield tmp_path
    fake_client.__exit__(None, None, None)


def _register_cc_via_http() -> str:
    """Register the agent directly through the fake client (sidesteps any
    ``coffer agent`` CLI verb naming this suite does not need to pin down).

    Returns its uid, which ``coffer memory context`` takes — that command is
    the one here whose caller is a machine rather than a person, so it is the
    one that does not resolve a name (see ``memory_cmd``'s docstring)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/agents", json={"type": "claude_code", "name": "cc"})
        assert r.status_code == 201, r.text
    return str(r.json()["uid"])


def _agent_uid(name: str) -> str:
    """The uid of an already-registered agent, by label — the same single
    lookup ``surfaces/cli/_resolve.py`` makes on a person's behalf."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/resources", params={"kind": "agent", "name": name})
        assert r.status_code == 200, r.text
    return str(r.json()["resources"][0]["uid"])


def _seed_repository(tmp_path: pathlib.Path) -> pathlib.Path:
    """A real repository with two Claude Code memory files in it: one about the
    project, one about the developer — which is the split that fills both a
    repository partition and ``global`` ("File personal entries into global")."""
    repository = init_repository(tmp_path / "coffer")
    claude_code_config(
        tmp_path / ".claude",
        repository,
        {"python-lockfile.md": _CC_PROJECT_MEMORY, "worktree-development.md": _CC_PERSONAL_MEMORY},
    )
    return repository


def _distilled_partition(tmp_path: pathlib.Path) -> str:
    """Register, seed, ``sync`` and ``distil`` — the state most tests start in."""
    _register_cc_via_http()
    # Every command below still names the partition by its LABEL: the CLI
    # resolves it to a uid itself, which is the whole point of `_resolve`.
    _seed_repository(tmp_path)
    synced = _runner.invoke(cli_app, ["memory", "sync", "--json"])
    assert synced.exit_code == 0, synced.output
    listed = _runner.invoke(cli_app, ["memory", "list", "--json"])
    partitions = json.loads(_extract_json(listed.output))["partitions"]
    name = next(p["name"] for p in partitions if p["name"] != "global")
    for partition in (name, "global"):
        distilled = _runner.invoke(cli_app, ["memory", "distil", partition])
        assert distilled.exit_code == 0, distilled.output
    return name


# ----- list, and the notes on disk ----------------------------------------


def _partition_dir(name: str) -> pathlib.Path:
    located = _runner.invoke(cli_app, ["path", "memory", name])
    assert located.exit_code == 0, located.output
    return pathlib.Path(located.output.strip().splitlines()[-1])


def test_sync_list_distil_and_the_note_on_disk(memory_cli_daemon):
    tmp_path = memory_cli_daemon
    _register_cc_via_http()
    repository = _seed_repository(tmp_path)

    synced = _runner.invoke(cli_app, ["memory", "sync", "--json"])
    assert synced.exit_code == 0, synced.output
    result = json.loads(_extract_json(synced.output))
    assert result["entries_written"] == 2
    assert result["failures"] == []
    # "Update memory in one action": the same call distilled what it read.
    assert sorted(result["distilled"]) == ["coffer", "global"]
    assert result["skipped"] == []

    listed = _runner.invoke(cli_app, ["memory", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    partitions = json.loads(_extract_json(listed.output))["partitions"]
    project = next(p for p in partitions if p["name"] != "global")
    assert project["name"] == "coffer"
    assert project["repository_path"] == str(repository.resolve())
    assert project["unresolvable"] is False

    # A second, hand-started pass finds nothing new: the update already opened
    # the note.
    distilled = _runner.invoke(cli_app, ["memory", "distil", project["name"]])
    assert distilled.exit_code == 0, distilled.output
    assert json.loads(_extract_json(distilled.output))["opened"] == 0

    # The note is a file: read where `coffer path memory` points.
    note = _partition_dir(project["name"]) / "notes" / "python-lockfile.md"
    assert "uv sync --frozen" in note.read_text(encoding="utf-8")

    table = _runner.invoke(cli_app, ["memory", "list"])
    assert table.exit_code == 0, table.output
    assert "coffer" in table.output


def test_list_table_calls_out_a_repository_that_is_gone(memory_cli_daemon):
    """Per "Report unresolvable partitions", an orphan is named as one rather
    than sitting there, listed and undeliverable, looking exactly like a live
    partition."""
    tmp_path = memory_cli_daemon
    partition = _distilled_partition(tmp_path)
    shutil.rmtree(tmp_path / "coffer")

    listed = _runner.invoke(cli_app, ["memory", "list"])

    assert listed.exit_code == 0, listed.output
    assert "unresolvable" in listed.output.replace("\n", "")
    assert partition in listed.output


def test_show_of_an_unknown_partition_exits_not_found(memory_cli_daemon):
    shown = _runner.invoke(cli_app, ["memory", "show", "does-not-exist"])
    combined = shown.output + (shown.stderr or "")
    assert shown.exit_code == 4, combined
    assert "Traceback" not in combined, combined


def test_show_edit_and_rm_a_partition(memory_cli_daemon):
    """The verbs every kind shares, on a partition; there is no `add`, and no
    switch (spec memory "Serve every partition to every agent")."""
    import typer.main

    partition = _distilled_partition(memory_cli_daemon)
    group = typer.main.get_command(cli_app).commands["memory"]  # type: ignore[attr-defined]
    assert not {"add", "enable", "disable"} & set(group.commands)

    shown = _runner.invoke(cli_app, ["memory", "show", partition, "--json"])
    assert shown.exit_code == 0, shown.output
    uid = json.loads(_extract_json(shown.output))["uid"]

    titled = _runner.invoke(cli_app, ["memory", "edit", partition, "--title", "Coffer repo"])
    assert titled.exit_code == 0, titled.output
    c, _info = _cli_client.client_or_exit()
    assert c.get(f"/resources/{uid}").json()["title"] == "Coffer repo"

    assert c.get(f"/resources/{uid}").json()["enabled"] is True

    removed = _runner.invoke(cli_app, ["memory", "rm", partition, "--yes"])
    assert removed.exit_code == 0, removed.output
    assert c.get(f"/resources/{uid}").status_code == 404


# ----- distil ---------------------------------------------------------------


def test_distil_of_an_unknown_partition_exits_not_found(memory_cli_daemon):
    distilled = _runner.invoke(cli_app, ["memory", "distil", "does-not-exist"])
    combined = distilled.output + (distilled.stderr or "")
    assert distilled.exit_code == 4, combined
    assert "Traceback" not in combined, combined


def test_distil_without_an_internal_connection_reports_the_mechanical_pass(memory_cli_daemon):
    """Per "Distil mechanically with no internal connection": thinner, not
    absent — the verb still returns a real pass, and says a model was not used
    rather than pretending one was.

    ``sync`` already ran the mechanical pass over ``global`` ("Update memory in
    one action"), which is what opened its note; the hand-started pass after it
    finds nothing new and still reports honestly."""
    tmp_path = memory_cli_daemon
    _register_cc_via_http()
    _seed_repository(tmp_path)
    synced = _runner.invoke(cli_app, ["memory", "sync", "--json"])
    assert "global" in json.loads(_extract_json(synced.output))["distilled"]
    assert len(list((_partition_dir("global") / "notes").glob("*.md"))) == 1

    distilled = _runner.invoke(cli_app, ["memory", "distil", "global"])

    assert distilled.exit_code == 0, distilled.output
    result = json.loads(_extract_json(distilled.output))
    assert result == {
        "partition": "global",
        "merged": 0,
        "opened": 0,
        "retired": 0,
        "dropped": 0,
        "model_used": False,
    }


# ----- `context`: the hook-invoked command, tested without client_or_exit --


def test_context_prints_nothing_and_exits_zero_when_no_daemon_is_running(monkeypatch):
    monkeypatch.setattr(memory_cmd, "live_daemon", lambda: None)
    result = _runner.invoke(
        cli_app, ["memory", "context", "--agent-uid", "some-uid", "--cwd", "/tmp"]
    )
    assert result.exit_code == 0
    assert result.output == ""


def test_context_prints_nothing_and_exits_zero_on_a_network_failure(monkeypatch):
    info = DaemonInfo(
        version=1, pid=1, port=1, token="t", started_at=dt.now(tz=UTC), binary_path="/test"
    )
    monkeypatch.setattr(memory_cmd, "live_daemon", lambda: info)

    def _raise(*args, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(memory_cmd.httpx, "post", _raise)
    result = _runner.invoke(
        cli_app, ["memory", "context", "--agent-uid", "some-uid", "--cwd", "/tmp"]
    )
    assert result.exit_code == 0
    assert result.output == ""


def test_context_prints_nothing_on_a_non_200_response(monkeypatch):
    info = DaemonInfo(
        version=1, pid=1, port=1, token="t", started_at=dt.now(tz=UTC), binary_path="/test"
    )
    monkeypatch.setattr(memory_cmd, "live_daemon", lambda: info)
    monkeypatch.setattr(
        memory_cmd.httpx,
        "post",
        lambda *a, **kw: httpx.Response(500, request=httpx.Request("POST", "http://x")),
    )
    result = _runner.invoke(
        cli_app, ["memory", "context", "--agent-uid", "some-uid", "--cwd", "/tmp"]
    )
    assert result.exit_code == 0
    assert result.output == ""


def _route_context_at_the_test_app(monkeypatch) -> None:
    """``context`` bypasses ``client_or_exit()`` and calls ``httpx.post``
    against a real socket (see the module docstring); nothing here binds one,
    so route that one call at the same in-process app the rest of this suite
    uses."""
    info = DaemonInfo(
        version=1, pid=1, port=59900, token=_TOKEN, started_at=dt.now(tz=UTC), binary_path="/test"
    )
    monkeypatch.setattr(memory_cmd, "live_daemon", lambda: info)
    real_client, _ = _cli_client.client_or_exit()

    def _fake_post(url, *, json=None, headers=None, timeout=None):
        path = url.split("/api/v1", 1)[1]
        return real_client.post(path, json=json)

    monkeypatch.setattr(memory_cmd.httpx, "post", _fake_post)


def _fires() -> int:
    c, _info = _cli_client.client_or_exit()
    r = c.get("/audit", params={"event_type": "memory_delivery_fired"})
    assert r.status_code == 200, r.text
    return len(r.json()["entries"])


def test_context_prints_the_whole_index_and_records_a_fire(memory_cli_daemon, monkeypatch):
    """What an installed session-start hook actually puts in front of an agent:
    a line per note and the absolute directory their bodies are in ("Deliver the
    index and the notes path at session start")."""
    tmp_path = memory_cli_daemon
    partition = _distilled_partition(tmp_path)
    _route_context_at_the_test_app(monkeypatch)
    cc_uid = _agent_uid("cc")

    assert _fires() == 0

    result = _runner.invoke(
        cli_app,
        ["memory", "context", "--agent-uid", cc_uid, "--cwd", str(tmp_path / "coffer")],
    )
    assert result.exit_code == 0, result.output
    assert "## Coffer memory" in result.output
    assert "`python-lockfile.md`" in result.output  # the repository's own note
    assert "`worktree-development.md`" in result.output  # and what is known about the developer
    assert str(tmp_path / "memory" / partition / "notes") in result.output
    assert "coffer__recall" not in result.output

    assert _fires() == 1


def test_context_of_a_partition_with_nothing_in_it_prints_nothing(memory_cli_daemon, monkeypatch):
    """An empty ``## Coffer memory`` header is worse than none, and this is the
    command a session-start hook runs on a vault that has never synced."""
    cc_uid = _register_cc_via_http()
    _route_context_at_the_test_app(monkeypatch)

    result = _runner.invoke(cli_app, ["memory", "context", "--agent-uid", cc_uid, "--cwd", "/tmp"])

    assert result.exit_code == 0, result.output
    assert result.output == ""
