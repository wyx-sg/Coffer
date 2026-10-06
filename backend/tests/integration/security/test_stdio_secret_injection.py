"""A stored secret bound to a stdio MCP server reaches its environment (spec secret, mcp-gateway).

A real daemon, the ledger server as the stdio upstream, and an agent speaking
JSON-RPC to ``/mcp``. The ledger's ``environment`` tool reports whether
``LEDGER_SECRET`` is set in the child, never its value.
"""

from __future__ import annotations

import json
import pathlib
import uuid
from collections.abc import Iterator

import pytest

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon
from tests.support.ledger_wire import call, events, ledger_transport, open_session, register, result

#: Built at run time so a secret scanner never sees a key-shaped literal here.
SECRET = "-".join(["ledger", "secret", "canary", "7f3a9c"])


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


def _mint(d: BoundaryDaemon) -> str:
    ref = "secret/" + uuid.uuid4().hex
    assert d.client.post("/api/v1/secrets", json={"ref": ref, "value": SECRET}).status_code == 204
    return ref


def test_a_secret_first_bound_reaches_the_stdio_server_s_environment(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    ref = _mint(daemon)
    uid = register(
        daemon,
        "ledger",
        ledger_transport(tmp_path / "ledger.jsonl", secret_refs={"LEDGER_SECRET": ref}),
    )
    assert daemon.pending(destination_uid=uid) == []
    session = open_session(daemon, "a" * 32)
    answer = result(call(daemon, session, "ledger__environment"))
    assert answer["structuredContent"]["secret_present"] is True
    assert not answer.get("isError")
    assert SECRET not in json.dumps(answer)


def test_a_second_destination_waits_for_approval_then_receives_the_secret(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    ref = _mint(daemon)
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    register(daemon, "first", ledger_transport(first, secret_refs={"LEDGER_SECRET": ref}))
    uid = register(daemon, "second", ledger_transport(second, secret_refs={"LEDGER_SECRET": ref}))
    [pending] = daemon.pending(destination_uid=uid)
    session = open_session(daemon, "a" * 32)

    refused = call(daemon, session, "second__environment")
    assert refused.status_code == 200
    error = refused.json()["error"]
    assert error["code"] == -32603
    assert "waiting for approval" in error["message"]
    assert f"coffer approval approve {pending['id']}" in error["message"]
    assert SECRET not in refused.text
    # The child never ran a tool: the call was refused before it got the secret.
    assert events(second, "start", "environment") == []

    daemon.approve(pending["id"])
    answer = result(call(daemon, session, "second__environment"))
    assert answer["structuredContent"]["secret_present"] is True
    assert SECRET not in json.dumps(answer)
    assert len(events(second, "start", "environment")) == 1
