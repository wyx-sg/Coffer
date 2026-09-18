"""Integration tests for `coffer resource` CLI subcommands."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime as dt
from typing import Any

import httpx
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app

_runner = CliRunner()

_ERROR_BODY = (
    '{"error": {"code": "INTERNAL_ERROR", "message": "internal server error", "details": {}}}'
)


# ---------------------------------------------------------------------------
# Helpers for 5xx error simulation
# ---------------------------------------------------------------------------


class _HttpErrorResponse:
    """Fake httpx response that raises HTTPStatusError on raise_for_status()."""

    def __init__(self, status_code: int = 500) -> None:
        self.status_code = status_code
        self._real = httpx.Response(status_code, text=_ERROR_BODY)

    def raise_for_status(self) -> None:
        req = httpx.Request("GET", "http://fake/api/v1/test")
        raise httpx.HTTPStatusError(
            f"Server error '{self.status_code}'",
            request=req,
            response=self._real,
        )

    def json(self) -> Any:
        return self._real.json()


class _ResolvedResponse:
    """A 200 carrying one match, so the label lookup can succeed."""

    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return {"resources": [{"uid": "uid-1", "kind": "fake_kind", "name": "anything"}]}


class _HttpErrorClient:
    """Fake client that returns a 5xx for the command's OWN request.

    The name lookup that now precedes every ``resource`` command (``_resolve``,
    a ``GET /resources?kind=&name=``) is answered normally instead. It has to
    be: what these tests are about is the command rendering a 5xx rather than
    raising, and a client that failed the lookup too would exit there and never
    reach the request under test — which is exactly how this test would rot
    into passing for the wrong reason.
    """

    def __init__(self, status_code: int = 500) -> None:
        self._status_code = status_code

    def get(self, path: str = "", *_args: Any, **_kwargs: Any) -> Any:
        if path == "/resources":
            return _ResolvedResponse()
        return _HttpErrorResponse(self._status_code)

    def post(self, *_args: Any, **_kwargs: Any) -> _HttpErrorResponse:
        return _HttpErrorResponse(self._status_code)

    def delete(self, *_args: Any, **_kwargs: Any) -> _HttpErrorResponse:
        return _HttpErrorResponse(self._status_code)

    def __enter__(self) -> _HttpErrorClient:
        return self

    def __exit__(self, *_: object) -> None:
        pass


_FAKE_INFO = DaemonInfo(
    version=1, pid=99, port=9999, token="t", started_at=dt.now(tz=UTC), binary_path="/fake"
)


def _register(in_proc_daemon, name: str = "r1", foo: int = 1) -> str:
    """Helper: register a fake_kind resource via the HTTP API (bypasses CLI).

    Returns the uid creation minted, for assertions that need the identity.
    The CLI itself never sees one — it takes the kind and the name a person
    typed and resolves them (``_resolve``) — so tests drive the commands the
    way the user does and use this only to check what was written.
    """
    from coffer.surfaces.cli import _client as _cli_client

    # Use the monkeypatched client directly
    client, _info = _cli_client.client_or_exit()
    r = client.post(
        "/resources",
        json={"kind": "fake_kind", "name": name, "config": {"foo": foo}},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


# ---------------------------------------------------------------------------
# resource list
# ---------------------------------------------------------------------------


def test_resource_list_empty(in_proc_daemon):
    result = _runner.invoke(app, ["resource", "list", "--json"])
    assert result.exit_code == 0, result.output
    import json

    data = json.loads(result.output)
    # Stable top-level key per spec scenario: `resources` for `resource list`.
    assert data == {"resources": []}


def test_resource_list_shows_registered(in_proc_daemon):
    uid = _register(in_proc_daemon)
    result = _runner.invoke(app, ["resource", "list", "--json"])
    assert result.exit_code == 0, result.output
    import json

    items = json.loads(result.output)["resources"]
    assert len(items) == 1
    # The row says which resource it is the way the surface now does: the kind
    # and the label a person reads, plus the uid a script acts on. The single
    # ``kind:name`` string this used to assert was the identity itself, and
    # there is no such spelling any more — these are the two halves it merged.
    assert items[0]["kind"] == "fake_kind"
    assert items[0]["name"] == "r1"
    assert items[0]["uid"] == uid


def test_resource_list_filter_kind(in_proc_daemon):
    _register(in_proc_daemon, name="r1")
    result = _runner.invoke(app, ["resource", "list", "--kind", "fake_kind", "--json"])
    assert result.exit_code == 0
    import json

    items = json.loads(result.output)["resources"]
    assert len(items) == 1


# ---------------------------------------------------------------------------
# resource show
# ---------------------------------------------------------------------------


def test_resource_show_existing(in_proc_daemon):
    uid = _register(in_proc_daemon)
    result = _runner.invoke(app, ["resource", "show", "fake_kind", "r1"])
    assert result.exit_code == 0, result.output
    # Same intent as the old ``"fake_kind:r1" in output``: the command echoes
    # back the resource the two arguments named. It now prints the uid beside
    # them, which is the one thing a caller cannot have typed.
    assert "fake_kind" in result.output
    assert "r1" in result.output
    assert uid in result.output


def test_resource_show_not_found(in_proc_daemon):
    result = _runner.invoke(app, ["resource", "show", "fake_kind", "nope"])
    # Exit 4 comes from the name lookup now, before any uid route is called —
    # the not-found answer a person gets names what they typed.
    assert result.exit_code == 4


# ---------------------------------------------------------------------------
# resource rename
# ---------------------------------------------------------------------------


def test_resource_rename_keeps_the_identity(in_proc_daemon):
    """A rename moves the label and nothing else.

    Available for every kind, which is the user-facing half of the identity
    change: while the name WAS the identity, moving it needed a route of its
    own and only one kind of the seven ever got one. The uid is asserted
    unchanged because that is what makes the rename cheap — every reference to
    this resource still resolves afterwards.
    """
    uid = _register(in_proc_daemon, name="r1")
    result = _runner.invoke(app, ["resource", "rename", "fake_kind", "r1", "r2"])
    assert result.exit_code == 0, result.output
    assert "r2" in result.output

    import json

    shown = _runner.invoke(app, ["resource", "show", "fake_kind", "r2", "--json"])
    assert shown.exit_code == 0, shown.output
    body = json.loads(shown.output)
    assert body["name"] == "r2"
    assert body["uid"] == uid  # same resource, new label

    # And the old label names nothing: a rename is a move, not a second name.
    assert _runner.invoke(app, ["resource", "show", "fake_kind", "r1"]).exit_code == 4


# ---------------------------------------------------------------------------
# resource enable / disable
# ---------------------------------------------------------------------------


def test_resource_enable_disable(in_proc_daemon):
    _register(in_proc_daemon)
    result = _runner.invoke(app, ["resource", "disable", "fake_kind", "r1"])
    assert result.exit_code == 0, result.output
    assert "disabled" in result.output

    result = _runner.invoke(app, ["resource", "enable", "fake_kind", "r1"])
    assert result.exit_code == 0, result.output
    assert "enabled" in result.output


# ---------------------------------------------------------------------------
# resource delete
# ---------------------------------------------------------------------------


def test_resource_delete_with_force(in_proc_daemon):
    _register(in_proc_daemon)
    result = _runner.invoke(app, ["resource", "delete", "--force", "fake_kind", "r1"])
    assert result.exit_code == 0, result.output
    assert "deleted" in result.output

    # Confirm gone
    result2 = _runner.invoke(app, ["resource", "show", "fake_kind", "r1"])
    assert result2.exit_code == 4


def test_resource_delete_not_found_with_force(in_proc_daemon):
    result = _runner.invoke(app, ["resource", "delete", "--force", "fake_kind", "ghost"])
    # No resource of that kind carries that label → the CLI's not-found code.
    assert result.exit_code == 4


# ---------------------------------------------------------------------------
# T2 — 5xx errors are rendered via check(), not bare raise_for_status()
# ---------------------------------------------------------------------------


def test_resource_show_5xx_renders_message_exits_nonzero(monkeypatch):
    """resource show on a 5xx response must NOT raise a Traceback; must exit non-zero."""
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_HttpErrorClient(), _FAKE_INFO))
    result = _runner.invoke(app, ["resource", "show", "fake_kind", "anything"])
    assert result.exit_code != 0, "expected non-zero exit on 5xx"
    assert "Traceback" not in (result.output or ""), "Traceback leaked to output"


def test_resource_delete_5xx_renders_message_exits_nonzero(monkeypatch):
    """resource delete on a 5xx response must NOT raise a Traceback; must exit non-zero."""
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_HttpErrorClient(), _FAKE_INFO))
    result = _runner.invoke(app, ["resource", "delete", "--force", "fake_kind", "anything"])
    assert result.exit_code != 0, "expected non-zero exit on 5xx"
    assert "Traceback" not in (result.output or ""), "Traceback leaked to output"
