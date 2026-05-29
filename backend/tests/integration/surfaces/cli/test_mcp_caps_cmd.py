"""Integration tests for `coffer mcp resource|prompt ...` curation commands
and the shared 404 branches in ``coffer.surfaces.cli._mcp_caps``.

Reuses the ``mcp_daemon`` fixture and ``_register_server`` helper defined in
``test_mcp_cmd.py`` so the same in-process daemon + stub discovery harness
applies here.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from typer.testing import CliRunner

from coffer.surfaces.cli.main import app

from .test_mcp_cmd import _register_server

# NOTE: the ``mcp_daemon`` fixture is re-exported via conftest.py so tests here
# request it by name without importing it (an import would shadow the param → F811).

_runner = CliRunner()


# ---------------------------------------------------------------------------
# _capabilities_for 404 branch (shared by tool/resource/prompt list)
#
# The real /capabilities route never 404s (it just queries discovery), so the
# CLI's 404 handler is exercised with a stub route that returns 404.
# ---------------------------------------------------------------------------


def _patch_caps_404(monkeypatch: Any) -> None:
    from fastapi import APIRouter, FastAPI, HTTPException
    from starlette.testclient import TestClient

    from coffer.infrastructure.daemon.pid_lock import DaemonInfo
    from coffer.surfaces.http import errors as _err
    from coffer.surfaces.http.auth import set_active_token as _set_token

    router = APIRouter(prefix="/api/v1/resources/mcp_server")

    @router.get("/{name}/capabilities")
    async def _caps(name: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
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


def test_tool_list_404_exits_4(monkeypatch: Any) -> None:
    """A 404 from GET /capabilities maps to CLI exit 4 with a clear message."""
    _patch_caps_404(monkeypatch)
    result = _runner.invoke(app, ["mcp", "tool", "list", "ghost"])
    assert result.exit_code == 4, result.output
    assert "not found" in (result.output + (result.stderr or ""))


def test_resource_list_404_exits_4(monkeypatch: Any) -> None:
    _patch_caps_404(monkeypatch)
    result = _runner.invoke(app, ["mcp", "resource", "list", "ghost"])
    assert result.exit_code == 4, result.output


def test_prompt_list_404_exits_4(monkeypatch: Any) -> None:
    _patch_caps_404(monkeypatch)
    result = _runner.invoke(app, ["mcp", "prompt", "list", "ghost"])
    assert result.exit_code == 4, result.output


# ---------------------------------------------------------------------------
# _toggle 404 branch (capability not found)
# ---------------------------------------------------------------------------


def test_tool_enable_unknown_capability_exits_4(mcp_daemon: Any) -> None:
    """Toggling a capability that has no preference row → 404 → exit 4."""
    _register_server()
    result = _runner.invoke(app, ["mcp", "tool", "enable", "fs", "no_such_tool"])
    assert result.exit_code == 4, result.output
    assert "capability not found" in (result.output + (result.stderr or ""))


def test_prompt_disable_unknown_capability_exits_4(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "prompt", "disable", "fs", "no_such_prompt"])
    assert result.exit_code == 4, result.output


# ---------------------------------------------------------------------------
# resource list --json / table (stub discovery yields one resource)
# ---------------------------------------------------------------------------


def test_resource_list_json_shape(mcp_daemon: Any) -> None:
    """`resource list --json` → object whose sole key is `resources` and which
    contains the stub-discovered resource."""
    _register_server()
    result = _runner.invoke(app, ["mcp", "resource", "list", "fs", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert list(payload.keys()) == ["resources"]
    uris = {r["original_uri"] for r in payload["resources"]}
    assert "file:///tmp/x" in uris
    assert "\x1b[" not in result.output, "ANSI escape leaked into --json output"


def test_resource_list_table(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "resource", "list", "fs"])
    assert result.exit_code == 0, result.output
    assert "file:///tmp/x" in result.output


# ---------------------------------------------------------------------------
# prompt list --json / table (stub discovery yields no prompts; assert shape)
# ---------------------------------------------------------------------------


def test_prompt_list_json_shape(mcp_daemon: Any) -> None:
    """`prompt list --json` → object whose sole key is `prompts`."""
    _register_server()
    result = _runner.invoke(app, ["mcp", "prompt", "list", "fs", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert list(payload.keys()) == ["prompts"]
    assert payload["prompts"] == []
    assert "\x1b[" not in result.output


def test_prompt_list_table(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "prompt", "list", "fs"])
    assert result.exit_code == 0, result.output
    # Empty prompt set still renders the titled table header.
    assert "fs prompts" in result.output


# ---------------------------------------------------------------------------
# prompt enable / disable success branches (seed a prompt preference row)
# ---------------------------------------------------------------------------


def _seed_prompt_pref(key: str) -> None:
    from datetime import UTC, datetime

    from coffer.domain.resource import ResourceRef
    from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceRepo
    from coffer.infrastructure.persistence.engine import (
        create_async_engine_with_pragmas,
        session_maker,
    )
    from coffer.infrastructure.persistence.repos import SqlAlchemyResourceRepo

    engine = create_async_engine_with_pragmas(os.environ["COFFER_DB_URL"])

    async def _seed() -> None:
        sm = session_maker(engine)
        resource = await SqlAlchemyResourceRepo(sm).find(ResourceRef("mcp_server", "fs"))
        assert resource is not None
        now = datetime.now(tz=UTC)
        await MCPCapabilityPreferenceRepo(sm).insert(resource.id, "prompt", key, True, now, now)
        await engine.dispose()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_seed())
    loop.close()


def test_prompt_disable_then_enable(mcp_daemon: Any) -> None:
    _register_server()
    _seed_prompt_pref("summarize")

    disabled = _runner.invoke(app, ["mcp", "prompt", "disable", "fs", "summarize"])
    assert disabled.exit_code == 0, disabled.output
    assert "disabled" in disabled.output

    enabled = _runner.invoke(app, ["mcp", "prompt", "enable", "fs", "summarize"])
    assert enabled.exit_code == 0, enabled.output
    assert "enabled" in enabled.output
