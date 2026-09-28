"""Integration tests for the error branches of `coffer mcp cap ...`
(``coffer.surfaces.cli._mcp_caps``) and its prompt/resource rows.

Reuses the ``mcp_daemon`` fixture and ``_register_server`` helper defined in
``test_mcp_cmd.py`` so the same in-process daemon + stub discovery harness
applies here.
"""

from __future__ import annotations

import json
from typing import Any

from typer.testing import CliRunner

from coffer.surfaces.cli.main import app

from .test_mcp_cmd import _register_server

# NOTE: the ``mcp_daemon`` fixture is re-exported via conftest.py so tests here
# request it by name without importing it (an import would shadow the param → F811).

_runner = CliRunner()


# ---------------------------------------------------------------------------
# the capabilities read 404s (shared by cap list / enable / disable)
#
# The stub resolves the name to a uid, then 404s on /capabilities — so this
# exercises the route-level 404 branch rather than the "no such server" one
# the lookup now answers first.
# ---------------------------------------------------------------------------


def _patch_caps_404(monkeypatch: Any) -> None:
    from fastapi import APIRouter, FastAPI, HTTPException
    from starlette.testclient import TestClient

    from coffer.infrastructure.daemon.pid_lock import DaemonInfo
    from coffer.surfaces.http import errors as _err
    from coffer.surfaces.http.auth import set_active_token as _set_token

    router = APIRouter(prefix="/api/v1")

    @router.get("/resources")
    async def _resolve(kind: str, name: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        return {"resources": [{"uid": "uid-ghost", "kind": kind, "name": name}]}

    @router.get("/resources/mcp_server/{uid}/capabilities")
    async def _caps(uid: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        raise HTTPException(status_code=404, detail="not found")

    from datetime import UTC
    from datetime import datetime as _dt

    stub_app = FastAPI()
    _err.register(stub_app)
    stub_app.include_router(router)
    _set_token("stub-token")
    info = DaemonInfo(
        version=1,
        pid=1,
        port=9999,
        token="stub-token",
        started_at=_dt.now(tz=UTC),
        binary_path="/test",
    )
    client = TestClient(
        stub_app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": "stub-token"},
        raise_server_exceptions=False,
    )
    from coffer.surfaces.cli import _client as _cli_client

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (client, info))


def test_cap_list_404_exits_4(monkeypatch: Any) -> None:
    """A 404 from GET /capabilities maps to CLI exit 4 with a clear message."""
    _patch_caps_404(monkeypatch)
    result = _runner.invoke(app, ["mcp", "cap", "list", "ghost"])
    assert result.exit_code == 4, result.output
    assert "not found" in (result.output + (result.stderr or ""))


def test_cap_disable_404_on_the_read_exits_4(monkeypatch: Any) -> None:
    _patch_caps_404(monkeypatch)
    result = _runner.invoke(app, ["mcp", "cap", "disable", "ghost", "tool:x"])
    assert result.exit_code == 4, result.output


# ---------------------------------------------------------------------------
# a ref the server does not offer
# ---------------------------------------------------------------------------


def test_cap_enable_unknown_tool_exits_4(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "cap", "enable", "fs", "tool:no_such_tool"])
    assert result.exit_code == 4, result.output
    assert "tool:no_such_tool" in (result.output + (result.stderr or ""))


def test_cap_disable_unknown_prompt_exits_4(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "cap", "disable", "fs", "prompt:no_such_prompt"])
    assert result.exit_code == 4, result.output


def test_cap_offered_but_never_recorded_exits_4(mcp_daemon: Any) -> None:
    """The server offers the tool, but no preference row exists for it (the
    toggle route's own 404): still exit 4, naming the capability."""
    _register_server()
    result = _runner.invoke(app, ["mcp", "cap", "disable", "fs", "tool:read_file"])
    assert result.exit_code == 4, result.output
    assert "capability not found: tool:read_file" in (result.output + (result.stderr or ""))


# ---------------------------------------------------------------------------
# --type resource / prompt (stub discovery yields one resource and no prompts)
# ---------------------------------------------------------------------------


def test_cap_list_resources_json_shape(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "cap", "list", "fs", "--type", "resource", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert list(payload.keys()) == ["resources"]
    assert {r["original_uri"] for r in payload["resources"]} == {"file:///tmp/x"}
    assert "\x1b[" not in result.output, "ANSI escape leaked into --json output"


def test_cap_list_prompts_json_shape(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "cap", "list", "fs", "--type", "prompt", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"prompts": []}


def test_cap_list_empty_type_renders_the_table(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "cap", "list", "fs", "--type", "prompt"])
    assert result.exit_code == 0, result.output
    assert "fs capabilities" in result.output
