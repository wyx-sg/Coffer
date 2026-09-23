"""Integration tests for ``coffer memory ...``.

See spec memory "Cover memory management on REST and the CLI".

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
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.memory import store as memory_store
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
  type: feedback
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
    listed = _runner.invoke(cli_app, ["memory", "partitions", "--json"])
    partitions = json.loads(_extract_json(listed.output))["partitions"]
    name = next(p["name"] for p in partitions if p["name"] != "global")
    for partition in (name, "global"):
        distilled = _runner.invoke(cli_app, ["memory", "distil", partition])
        assert distilled.exit_code == 0, distilled.output
    return name


# ----- partitions, notes, one note ------------------------------------------


def test_sync_then_partitions_notes_and_one_note(memory_cli_daemon):
    tmp_path = memory_cli_daemon
    _register_cc_via_http()
    repository = _seed_repository(tmp_path)

    synced = _runner.invoke(cli_app, ["memory", "sync", "--json"])
    assert synced.exit_code == 0, synced.output
    result = json.loads(_extract_json(synced.output))
    assert result["entries_written"] == 2
    assert result["failures"] == []

    listed = _runner.invoke(cli_app, ["memory", "partitions", "--json"])
    assert listed.exit_code == 0, listed.output
    partitions = json.loads(_extract_json(listed.output))["partitions"]
    project = next(p for p in partitions if p["name"] != "global")
    assert project["name"] == "coffer"
    assert project["repository_path"] == str(repository.resolve())
    assert project["unresolvable"] is False

    distilled = _runner.invoke(cli_app, ["memory", "distil", project["name"]])
    assert distilled.exit_code == 0, distilled.output
    assert json.loads(_extract_json(distilled.output))["opened"] == 1

    notes = _runner.invoke(cli_app, ["memory", "notes", project["name"], "--json"])
    assert notes.exit_code == 0, notes.output
    note = json.loads(_extract_json(notes.output))["notes"][0]
    assert note["title"] == "python-lockfile"
    assert note["slug"] == "python-lockfile"
    assert note["type"] == "project"

    table = _runner.invoke(cli_app, ["memory", "notes", project["name"]])
    assert table.exit_code == 0, table.output
    assert "python-lockfile" in table.output.replace("\n", "")

    shown = _runner.invoke(cli_app, ["memory", "note", project["name"], note["slug"]])
    assert shown.exit_code == 0, shown.output
    assert "uv sync --frozen" in shown.output
    # The origin is printed because a note's body is Coffer's paraphrase
    # ("Write notes in Coffer's own words"): a note that reads wrong has to be
    # traceable to what said it.
    assert "origin: cc <-" in shown.output


def test_partitions_table_calls_out_a_repository_that_is_gone(memory_cli_daemon):
    """Per "Report unresolvable partitions", an orphan is named as one rather
    than sitting there, listed and undeliverable, looking exactly like a live
    partition."""
    tmp_path = memory_cli_daemon
    partition = _distilled_partition(tmp_path)
    shutil.rmtree(tmp_path / "coffer")

    listed = _runner.invoke(cli_app, ["memory", "partitions"])

    assert listed.exit_code == 0, listed.output
    assert "unresolvable" in listed.output.replace("\n", "")
    assert partition in listed.output


def test_notes_of_an_unknown_partition_exits_not_found(memory_cli_daemon):
    notes = _runner.invoke(cli_app, ["memory", "notes", "does-not-exist"])
    combined = notes.output + (notes.stderr or "")
    assert notes.exit_code == 4, combined
    assert "Traceback" not in combined, combined


def test_note_that_is_not_there_exits_not_found(memory_cli_daemon):
    partition = _distilled_partition(memory_cli_daemon)

    shown = _runner.invoke(cli_app, ["memory", "note", partition, "no-such-note"])

    combined = shown.output + (shown.stderr or "")
    assert shown.exit_code == 4, combined
    assert "Traceback" not in combined, combined


# ----- retired --------------------------------------------------------------


def test_retired_prints_what_was_retired_and_why(memory_cli_daemon):
    """``RETIRED.md`` is the only thing that makes a deletion stick in a store
    whose sources live outside it ("Record retirements so they stick"), so it has
    a verb of its own."""
    partition = _distilled_partition(memory_cli_daemon)
    empty = _runner.invoke(cli_app, ["memory", "retired", partition, "--json"])
    assert json.loads(_extract_json(empty.output))["retired"] == []

    memory_store.write_retired(
        partition,
        [
            RetiredNote(
                slug="hook-injection",
                title="Context injection ships",
                reason="The mechanism was removed.",
                replaced_by="pull-only-delivery",
                retired_at="2026-09-10T00:00:00+00:00",
                entry_ids=("cc:one",),
            )
        ],
    )

    listed = _runner.invoke(cli_app, ["memory", "retired", partition])
    assert listed.exit_code == 0, listed.output
    # Rich wraps long cells, so the table is asserted on values short enough to
    # survive a column rather than on the prose it wraps.
    flat = listed.output.replace("\n", "")
    assert "hook-injection" in flat
    assert "removed" in flat

    as_json = _runner.invoke(cli_app, ["memory", "retired", partition, "--json"])
    record = json.loads(_extract_json(as_json.output))["retired"][0]
    assert record["slug"] == "hook-injection"
    assert record["reason"] == "The mechanism was removed."


# ----- distil ---------------------------------------------------------------


def test_distil_of_an_unknown_partition_exits_not_found(memory_cli_daemon):
    distilled = _runner.invoke(cli_app, ["memory", "distil", "does-not-exist"])
    combined = distilled.output + (distilled.stderr or "")
    assert distilled.exit_code == 4, combined
    assert "Traceback" not in combined, combined


def test_distil_without_an_internal_connection_reports_the_mechanical_pass(memory_cli_daemon):
    """Per "Distil mechanically with no internal connection": thinner, not
    absent — the verb still returns a real pass, and says a model was not used
    rather than pretending one was."""
    tmp_path = memory_cli_daemon
    _register_cc_via_http()
    _seed_repository(tmp_path)
    _runner.invoke(cli_app, ["memory", "sync", "--json"])

    distilled = _runner.invoke(cli_app, ["memory", "distil", "global"])

    assert distilled.exit_code == 0, distilled.output
    result = json.loads(_extract_json(distilled.output))
    assert result == {
        "partition": "global",
        "merged": 0,
        "opened": 1,
        "retired": 0,
        "dropped": 0,
        "model_used": False,
    }


# ----- delivery -------------------------------------------------------------


def test_delivery_install_status_and_remove_round_trip(memory_cli_daemon):
    _register_cc_via_http()

    installed = _runner.invoke(cli_app, ["memory", "delivery-install", "cc"])
    assert installed.exit_code == 0, installed.output
    assert json.loads(_extract_json(installed.output))["installed"] is True

    status = _runner.invoke(cli_app, ["memory", "delivery", "--json"])
    data = json.loads(_extract_json(status.output))["delivery"]
    # The row carries both: the label a person reads, and the identity a script
    # would act on.
    row = next(d for d in data if d["agent_name"] == "cc")
    assert row["installed"] is True
    assert row["agent_uid"]

    narrowed = _runner.invoke(cli_app, ["memory", "delivery", "--agent", "cc", "--json"])
    assert narrowed.exit_code == 0, narrowed.output
    assert len(json.loads(_extract_json(narrowed.output))["delivery"]) == 1

    removed = _runner.invoke(cli_app, ["memory", "delivery-remove", "cc"])
    assert removed.exit_code == 0, removed.output
    assert json.loads(_extract_json(removed.output))["installed"] is False

    table = _runner.invoke(cli_app, ["memory", "delivery"])
    assert table.exit_code == 0, table.output
    assert "cc" in table.output


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


def test_context_prints_the_whole_index_and_records_a_fire(memory_cli_daemon, monkeypatch):
    """What an installed session-start hook actually puts in front of an agent:
    a line per note and the absolute directory their bodies are in ("Deliver the
    index and the notes path at session start")."""
    tmp_path = memory_cli_daemon
    partition = _distilled_partition(tmp_path)
    _route_context_at_the_test_app(monkeypatch)
    cc_uid = _agent_uid("cc")

    before = _runner.invoke(cli_app, ["audit", "list", "--json"])
    assert "memory_delivery_fired" not in before.output

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

    after = _runner.invoke(cli_app, ["audit", "list", "--json"])
    assert "memory_delivery_fired" in after.output


def test_context_of_a_partition_with_nothing_in_it_prints_nothing(memory_cli_daemon, monkeypatch):
    """An empty ``## Coffer memory`` header is worse than none, and this is the
    command a session-start hook runs on a vault that has never synced."""
    cc_uid = _register_cc_via_http()
    _route_context_at_the_test_app(monkeypatch)

    result = _runner.invoke(cli_app, ["memory", "context", "--agent-uid", cc_uid, "--cwd", "/tmp"])

    assert result.exit_code == 0, result.output
    assert result.output == ""


# ----- `ls` / `read`: the partition's own directory from the terminal -------
#
# The REST half has existed since "Present partitions as a table and a file
# tree" (GET /memory/partitions/{uid}/files and .../files/content) but `coffer
# memory` could reach notes and partitions and not the files they are stored in,
# which is the one thing "Cover memory management on REST and the CLI" names
# that the group did not do. The verbs are `ls` and `read` so that browsing
# memory and browsing knowledge are the same two words.


def test_ls_walks_a_partitions_own_directory(memory_cli_daemon):
    partition = _distilled_partition(memory_cli_daemon)

    listed = _runner.invoke(cli_app, ["memory", "ls", partition, "--json"])
    assert listed.exit_code == 0, listed.output
    root = json.loads(_extract_json(listed.output))["root"]
    assert root["path"] == ""
    children = {child["name"]: child for child in root["children"]}
    assert set(children) == {"MEMORY.md", "notes", ".raw"}
    assert children["notes"]["type"] == "dir"
    assert "notes/python-lockfile.md" in {c["path"] for c in children["notes"]["children"]}
    # `.raw/` is reachable and flagged as the verbatim input ("Keep raw entries
    # verbatim and hidden", "Present partitions as a table and a file tree").
    assert children[".raw"]["derived"] is True
    assert children["notes"]["derived"] is False


def test_ls_renders_the_whole_tree_as_a_table_by_default(memory_cli_daemon):
    """The default rendering is the tree, not just its top level: a partition
    is two levels deep by construction (``notes/<slug>.md``), so a listing that
    stopped at the root would never show a note."""
    partition = _distilled_partition(memory_cli_daemon)

    listed = _runner.invoke(cli_app, ["memory", "ls", partition])

    assert listed.exit_code == 0, listed.output
    flat = listed.output.replace("\n", "")
    assert "notes/python-lockfile.md" in flat
    assert "(derived)" in flat  # `.raw/` is named as the input it is


def test_read_prints_one_file_from_a_partition(memory_cli_daemon):
    partition = _distilled_partition(memory_cli_daemon)

    read = _runner.invoke(cli_app, ["memory", "read", partition, "notes/python-lockfile.md"])

    assert read.exit_code == 0, read.output
    assert "uv sync --frozen" in read.output


def test_read_prints_the_index_a_session_is_given(memory_cli_daemon):
    partition = _distilled_partition(memory_cli_daemon)

    read = _runner.invoke(cli_app, ["memory", "read", partition, "MEMORY.md"])

    assert read.exit_code == 0, read.output
    assert "python-lockfile" in read.output


def test_read_json_carries_the_paths_the_viewer_needs(memory_cli_daemon):
    partition = _distilled_partition(memory_cli_daemon)

    read = _runner.invoke(
        cli_app, ["memory", "read", partition, "notes/python-lockfile.md", "--json"]
    )

    assert read.exit_code == 0, read.output
    data = json.loads(_extract_json(read.output))
    assert data["path"] == "notes/python-lockfile.md"
    assert data["abs_path"].endswith("/notes/python-lockfile.md")
    assert data["folder_abs_path"].endswith(f"/{partition}/notes")
    assert data["binary"] is False


def test_read_of_a_missing_file_exits_not_found_without_a_traceback(memory_cli_daemon):
    partition = _distilled_partition(memory_cli_daemon)

    read = _runner.invoke(cli_app, ["memory", "read", partition, "notes/no-such-note.md"])

    combined = read.output + (read.stderr or "")
    assert read.exit_code == 4, combined
    assert "Traceback" not in combined, combined


def test_read_of_a_path_escaping_the_partition_is_refused(memory_cli_daemon):
    partition = _distilled_partition(memory_cli_daemon)

    read = _runner.invoke(cli_app, ["memory", "read", partition, "../../../../etc/passwd"])

    combined = read.output + (read.stderr or "")
    assert read.exit_code == 6, combined
    assert "Traceback" not in combined, combined
