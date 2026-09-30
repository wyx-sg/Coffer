"""Integration tests for ``coffer memory ...``.

See spec memory "Cover memory management on REST and the CLI": the lifecycle
verbs (no ``add``) and ``sync``, plus the session-start fire of ``hook``.
Notes, the index and the retirement record are plain files that ``coffer path
memory`` names (test_path_cmd.py), so no command here reads one.

Most commands are thin HTTP shells, tested the same way
``test_knowledge_cmd.py`` tests its own: boot the real app, route
``_cli_client.client_or_exit`` at a ``TestClient`` over it. ``hook`` never
goes through ``client_or_exit``'s detect-or-spawn, so its one call is routed
by monkeypatching ``live_daemon``/``httpx.post`` directly.

The fixture repository is a **real** ``git init``, because a partition is keyed
on a repository and a plain directory deliberately earns none ("Identify a partition
by its repository", "Create no partition for a non-repository directory");
and every test that wants notes runs ``sync``, which aggregates **then**
distils, because aggregation alone writes only the hidden ``.raw/`` and the
notes are the distil pass's output ("Keep raw entries verbatim and hidden").
With no internal connection configured that pass is the mechanical one — one
note per entry, and an index over them ("Distil mechanically with no internal
connection").
"""

from __future__ import annotations

import json
import pathlib
import shutil
from datetime import UTC
from datetime import datetime as dt

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
import coffer.surfaces.cli.memory_hook_cmd as memory_hook_cmd
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

    Returns its uid, which ``coffer memory hook`` takes — its caller is a
    machine rather than a person, so it does not resolve a name."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/agents", json={"type": "claude_code"})
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
    """Register, seed and ``sync`` — which distils what it read ("Update memory
    in one action") — the state most tests start in."""
    _register_cc_via_http()
    # Every command below still names the partition by its LABEL: the CLI
    # resolves it to a uid itself, which is the whole point of `_resolve`.
    _seed_repository(tmp_path)
    synced = _runner.invoke(cli_app, ["memory", "sync", "--json"])
    assert synced.exit_code == 0, synced.output
    listed = _runner.invoke(cli_app, ["memory", "list", "--json"])
    partitions = json.loads(_extract_json(listed.output))["partitions"]
    return next(p["name"] for p in partitions if p["name"] != "global")


# ----- list, and the notes on disk ----------------------------------------


def _partition_dir(name: str) -> pathlib.Path:
    located = _runner.invoke(cli_app, ["path", "memory", name])
    assert located.exit_code == 0, located.output
    return pathlib.Path(located.output.strip().splitlines()[-1])


def test_sync_list_and_the_note_on_disk(memory_cli_daemon):
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

    # A second update finds nothing new to distil: the first already opened
    # the note.
    again = _runner.invoke(cli_app, ["memory", "sync", "--json"])
    assert again.exit_code == 0, again.output
    assert json.loads(_extract_json(again.output))["distilled"] == []

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


# ----- `hook` at session start, routed at the in-process app ----------------


def _route_hook_at_the_test_app(monkeypatch) -> None:
    """``hook`` bypasses ``client_or_exit()`` and calls ``httpx.post`` against
    a real socket; nothing here binds one, so route that one call at the same
    in-process app the rest of this suite uses."""
    info = DaemonInfo(
        version=1, pid=1, port=59900, token=_TOKEN, started_at=dt.now(tz=UTC), binary_path="/test"
    )
    monkeypatch.setattr(memory_hook_cmd, "live_daemon", lambda: info)
    real_client, _ = _cli_client.client_or_exit()

    def _fake_post(url, *, json=None, headers=None, timeout=None):
        path = url.split("/api/v1", 1)[1]
        return real_client.post(path, json=json)

    monkeypatch.setattr(memory_hook_cmd.httpx, "post", _fake_post)


def _fires() -> int:
    c, _info = _cli_client.client_or_exit()
    r = c.get("/audit", params={"event_type": "memory_delivery_fired"})
    assert r.status_code == 200, r.text
    return len(r.json()["entries"])


@pytest.mark.acceptance(
    spec="memory", scenario="a Codex hook fire prints the session-start JSON Codex reads"
)
def test_a_codex_session_start_fire_prints_that_events_json(memory_cli_daemon, monkeypatch):
    """What Codex's installed SessionStart hook prints: the composed index as
    ``hookSpecificOutput.additionalContext``, the shape Codex hands to the
    model as a developer message. The fire is recorded."""
    tmp_path = memory_cli_daemon
    _distilled_partition(tmp_path)
    _route_hook_at_the_test_app(monkeypatch)
    cc_uid = _agent_uid("claude-code")
    event = {
        "hook_event_name": "SessionStart",
        "session_id": "s-1",
        "cwd": str(tmp_path / "coffer"),
        "source": "startup",
    }

    assert _fires() == 0
    result = _runner.invoke(
        cli_app, ["memory", "hook", "--agent-uid", cc_uid], input=json.dumps(event)
    )
    assert result.exit_code == 0, result.output
    out = json.loads(result.output)
    assert set(out) == {"hookSpecificOutput"}
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    context = out["hookSpecificOutput"]["additionalContext"]
    assert context.startswith("## Coffer memory")
    assert "`python-lockfile.md`" in context
    assert _fires() == 1
