"""Integration tests for `coffer agent native-memory` / `import-native-memory`.

FR-009 requires every agent-workspace op to exist on BOTH REST and CLI; these
two verbs wrap the spec-004 routes (FR-040/FR-041):

  * ``GET  /agents/{name}/native-memory``         → ``native-memory``
  * ``POST /agents/{name}/native-memory/import``  → ``import-native-memory``

The native-memory service needs on-disk git repos and decoded project slugs to
produce a non-trivial result, which is awkward to set up deterministically in a
CLI test. So — like the rest of the CLI suite — we stub the HTTP layer: a tiny
fake client returns canned ``GET``/``POST`` responses, and
``_client.client_or_exit`` is monkeypatched to hand it back. No daemon, no LLM,
no disk: the test exercises only the CLI's request shaping, ``--json`` handling,
table rendering, and one-line summaries.
"""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime as dt
from typing import Any

import pytest
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app

_runner = CliRunner()


class _FakeResponse:
    """Minimal stand-in for ``httpx.Response`` as the CLI consumes it."""

    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = b"x"

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        # The two verbs only hit happy/404 paths covered by the routes; any 4xx
        # here would surface through ``_cli_client.check`` like the real client.
        if self.status_code >= 400:  # pragma: no cover - not exercised
            import httpx

            request = httpx.Request("GET", "http://test/")
            raise httpx.HTTPStatusError(
                "error",
                request=request,
                response=httpx.Response(self.status_code, json=self._payload, request=request),
            )


class _FakeClient:
    """Records GET/POST calls and replays canned responses keyed by path."""

    def __init__(self, get_map: dict[str, _FakeResponse], post_map: dict[str, _FakeResponse]):
        self._get_map = get_map
        self._post_map = post_map
        self.calls: list[tuple[str, str, Any]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get(self, path: str, **kw: Any) -> _FakeResponse:
        self.calls.append(("GET", path, kw))
        return self._get_map[path]

    def post(self, path: str, **kw: Any) -> _FakeResponse:
        self.calls.append(("POST", path, kw.get("json")))
        return self._post_map[path]


def _install(monkeypatch, *, get_map=None, post_map=None) -> _FakeClient:
    client = _FakeClient(get_map or {}, post_map or {})
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


# ---------------------------------------------------------------------------
# agent native-memory
# ---------------------------------------------------------------------------


def test_native_memory_json(monkeypatch):
    """`native-memory <name> --json` prints the raw items array verbatim."""
    items = [
        {"project": "demo", "path": "/x/demo", "memory_dir": "/x/.claude/p/m", "item_count": 3},
        {"project": "lib", "path": None, "memory_dir": "/x/.claude/q/m", "item_count": 0},
    ]
    client = _install(
        monkeypatch, get_map={"/agents/cc/native-memory": _FakeResponse(200, {"items": items})}
    )

    result = _runner.invoke(cli_app, ["agent", "native-memory", "cc", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == items
    assert client.calls == [("GET", "/agents/cc/native-memory", {})]


def test_native_memory_table(monkeypatch):
    """`native-memory <name>` renders a table with project/items/path columns."""
    items = [
        {"project": "demo", "path": "/x/demo", "memory_dir": "/x/.claude/p/m", "item_count": 3},
    ]
    _install(
        monkeypatch, get_map={"/agents/cc/native-memory": _FakeResponse(200, {"items": items})}
    )

    result = _runner.invoke(cli_app, ["agent", "native-memory", "cc"])
    assert result.exit_code == 0, result.output
    assert "demo" in result.output
    assert "/x/demo" in result.output
    # Column header for the item count is present.
    assert "Items" in result.output


def test_native_memory_empty(monkeypatch):
    """An empty store list prints the friendly placeholder, not an empty table."""
    _install(monkeypatch, get_map={"/agents/cc/native-memory": _FakeResponse(200, {"items": []})})

    result = _runner.invoke(cli_app, ["agent", "native-memory", "cc"])
    assert result.exit_code == 0, result.output
    assert "no native memory" in result.output


# ---------------------------------------------------------------------------
# agent import-native-memory
# ---------------------------------------------------------------------------


def test_import_native_memory_success(monkeypatch):
    """A successful import prints a one-line `imported N (skipped M) into <store>` summary."""
    payload = {
        "imported": 2,
        "skipped": 1,
        "store": "project-demo",
        "project_path": "/x/demo",
        "organized": True,
    }
    client = _install(
        monkeypatch,
        post_map={"/agents/cc/native-memory/import": _FakeResponse(200, payload)},
    )

    result = _runner.invoke(cli_app, ["agent", "import-native-memory", "cc", "/x/.claude/p/m"])
    assert result.exit_code == 0, result.output
    assert "imported 2" in result.output
    assert "skipped 1" in result.output
    assert "project-demo" in result.output
    # The memory_dir was forwarded in the POST body.
    assert client.calls == [
        ("POST", "/agents/cc/native-memory/import", {"memory_dir": "/x/.claude/p/m"})
    ]


def test_import_native_memory_not_mapped(monkeypatch):
    """A null store (not a git project) prints the could-not-map message."""
    payload = {
        "imported": 0,
        "skipped": 0,
        "store": None,
        "project_path": None,
        "organized": False,
    }
    _install(
        monkeypatch,
        post_map={"/agents/cc/native-memory/import": _FakeResponse(200, payload)},
    )

    result = _runner.invoke(cli_app, ["agent", "import-native-memory", "cc", "/x/orphan/m"])
    assert result.exit_code == 0, result.output
    assert "could not map" in result.output


@pytest.mark.acceptance(spec="004-agent-registry", scenario="CLI surface mirrors REST operations")
def test_native_memory_and_import_are_registered():
    """Both verbs appear under `coffer agent` (FR-009 CLI/REST parity)."""
    help_out = _runner.invoke(cli_app, ["agent", "--help"]).output
    assert "native-memory" in help_out
    assert "import-native-memory" in help_out
