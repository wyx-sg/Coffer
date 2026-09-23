"""Integration tests for `coffer agent native-memory`.

spec agent-registry "Expose every agent operation through REST, CLI and the Agents page"
requires every agent-workspace op to exist on BOTH REST and CLI;
this verb wraps the one read-only route:

  ``GET /agents/{uid}/native-memory`` → ``native-memory``

The verb still TAKES a name; the route is addressed by uid
(ADR resource-identity-is-an-immutable-uid). Each invocation is therefore two
requests: ``GET /resources?kind=agent&name=<name>`` to turn the typed name into
a uid, then the native-memory route under that uid.

The native-memory service needs on-disk project trees and decoded slugs to
produce a non-trivial result, which is awkward to set up deterministically in a
CLI test. So — like the rest of the CLI suite — we stub the HTTP layer: a tiny
fake client returns canned ``GET`` responses, serves the name lookup from a
``name -> uid`` registry, and ``_client.client_or_exit`` is monkeypatched to
hand it back. No daemon, no disk: the test exercises only the CLI's request
shaping, ``--json`` handling and table rendering.
"""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime as dt
from typing import Any

from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app

_runner = CliRunner()

#: The uid the fake registry hands back for the agent named ``cc``. Opaque on
#: purpose — nothing in the CLI may derive it from the name.
CC_UID = "b82d7e5a31f44c6d9a0e5b7c2d13f486"


class _FakeResponse:
    """Minimal stand-in for ``httpx.Response`` as the CLI consumes it."""

    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = b"x"

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:  # pragma: no cover - not exercised
            import httpx

            request = httpx.Request("GET", "http://test/")
            raise httpx.HTTPStatusError(
                "error",
                request=request,
                response=httpx.Response(self.status_code, json=self._payload, request=request),
            )


class _FakeClient:
    """Records GET calls and replays canned responses keyed by path.

    It also stands in for the resource registry, since the command's first
    request is always the name → uid lookup. ``agents`` is the ``name -> uid``
    table that ``GET /resources?kind=agent&name=`` is answered from; a name
    missing from it yields the empty match list a real daemon would return,
    which is how a test says "no such agent".
    """

    def __init__(self, get_map: dict[str, _FakeResponse], agents: dict[str, str]):
        self._get_map = get_map
        self._agents = agents
        self.calls: list[tuple[str, str, Any]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get(self, path: str, **kw: Any) -> _FakeResponse:
        self.calls.append(("GET", path, kw))
        if path == "/resources":
            return self._resolve(kw.get("params") or {})
        return self._get_map[path]

    def _resolve(self, params: dict[str, Any]) -> _FakeResponse:
        """The name → uid lookup, shaped exactly like the real list route."""
        name = params.get("name")
        uid = self._agents.get(str(name))
        matches = [] if uid is None else [{"uid": uid, "kind": params.get("kind"), "name": name}]
        return _FakeResponse(200, {"resources": matches})


def _install(monkeypatch, *, get_map=None, agents=None) -> _FakeClient:
    """Install the fake client. ``agents`` defaults to the one agent the
    happy-path tests use; pass ``{}`` for a registry that holds nobody."""
    client = _FakeClient(get_map or {}, {"cc": CC_UID} if agents is None else agents)
    info = DaemonInfo(
        version=1,
        pid=1,
        port=8000,
        token="t",
        started_at=dt.now(tz=UTC),
        binary_path="/t",
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (client, info))
    return client


def test_native_memory_json(monkeypatch):
    """`native-memory <name> --json` prints the raw items array verbatim."""
    items = [
        {"project": "demo", "path": "/x/demo", "memory_dir": "/x/.claude/p/m", "item_count": 3},
        {"project": "lib", "path": None, "memory_dir": "/x/.claude/q/m", "item_count": 0},
    ]
    client = _install(
        monkeypatch,
        get_map={f"/agents/{CC_UID}/native-memory": _FakeResponse(200, {"items": items})},
    )

    result = _runner.invoke(cli_app, ["agent", "native-memory", "cc", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == items
    # Two calls, in order: resolve the typed name, then read under the uid.
    assert client.calls == [
        ("GET", "/resources", {"params": {"kind": "agent", "name": "cc"}}),
        ("GET", f"/agents/{CC_UID}/native-memory", {}),
    ]


def test_native_memory_table(monkeypatch):
    """`native-memory <name>` renders a table with project/items/path columns."""
    items = [
        {"project": "demo", "path": "/x/demo", "memory_dir": "/x/.claude/p/m", "item_count": 3},
    ]
    _install(
        monkeypatch,
        get_map={f"/agents/{CC_UID}/native-memory": _FakeResponse(200, {"items": items})},
    )

    result = _runner.invoke(cli_app, ["agent", "native-memory", "cc"])
    assert result.exit_code == 0, result.output
    assert "demo" in result.output
    assert "/x/demo" in result.output
    # Column header for the item count is present.
    assert "Items" in result.output


def test_native_memory_empty(monkeypatch):
    """An empty store list prints the friendly placeholder, not an empty table."""
    _install(
        monkeypatch,
        get_map={f"/agents/{CC_UID}/native-memory": _FakeResponse(200, {"items": []})},
    )

    result = _runner.invoke(cli_app, ["agent", "native-memory", "cc"])
    assert result.exit_code == 0, result.output
    assert "no native memory" in result.output


def test_native_memory_unknown_agent_exits_4(monkeypatch):
    """A name nobody holds exits 4 before the native-memory route is touched.

    Same exit code as before, different source: the refusal used to be a 404
    from the route and is now the name → uid lookup finding nothing
    (``_resolve.resolve``). The message is asserted because that is the part
    that actually changed — it names the kind and the string the user typed,
    which a 404 on an opaque uid could not.
    """
    client = _install(monkeypatch, agents={})

    result = _runner.invoke(cli_app, ["agent", "native-memory", "ghost"])
    assert result.exit_code == 4, result.output
    assert "no agent named 'ghost'" in result.output
    assert client.calls == [("GET", "/resources", {"params": {"kind": "agent", "name": "ghost"}})]


def test_native_memory_is_registered():
    """The read verb appears under `coffer agent` (spec agent-registry CLI/REST parity)."""
    help_out = _runner.invoke(cli_app, ["agent", "--help"]).output
    assert "native-memory" in help_out
