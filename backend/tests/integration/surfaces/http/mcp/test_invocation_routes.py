"""Integration tests for MCP invocation log query route."""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.domain.mcp.capability import MCPInvocation
from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_invocation_repo
from coffer.surfaces.http.mcp.invocation_routes import router as invocation_router


def _make_invocation(
    resource_name: str,
    capability_key: str = "read_file",
    status: str = "ok",
    duration_ms: int = 10,
    offset_seconds: int = 0,
    session_id: str | None = None,
) -> MCPInvocation:
    return MCPInvocation(
        id=None,
        timestamp=datetime.now(tz=UTC) - timedelta(seconds=offset_seconds),
        resource_name=resource_name,
        capability_type="tool",
        capability_key=capability_key,
        duration_ms=duration_ms,
        status=status,  # type: ignore[arg-type]
        error_message="boom" if status == "error" else None,
        session_id=session_id,
    )


async def _build_app(
    tmp_path: Path,
) -> tuple[FastAPI, Any, MCPInvocationRepo]:
    """Build a minimal FastAPI app wired for invocation route tests."""
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    inv_repo = MCPInvocationRepo(sm)

    set_active_token("test-token")

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(invocation_router)
    app.dependency_overrides[get_invocation_repo] = lambda: inv_repo

    return app, engine, inv_repo


@pytest.fixture
async def inv_client(tmp_path: Path):
    """Yield (client, engine, inv_repo)."""
    app, engine, inv_repo = await _build_app(tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Coffer-Token": "test-token"},
    ) as client:
        yield client, engine, inv_repo

    with suppress(BaseException):
        await engine.dispose()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_invocations_list(inv_client: tuple) -> None:
    client, _engine, _repo = inv_client
    r = await client.get("/api/v1/resources/mcp_server/fs/invocations")
    assert r.status_code == 200, r.text
    assert r.json() == {"invocations": []}


@pytest.mark.asyncio
async def test_invocations_requires_auth(tmp_path: Path) -> None:
    app, engine, _repo = await _build_app(tmp_path)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "bad-token"},
        ) as client:
            r = await client.get("/api/v1/resources/mcp_server/fs/invocations")
            assert r.status_code == 401
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Basic retrieval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invocations_returned_after_insert(inv_client: tuple) -> None:
    client, _engine, repo = inv_client
    await repo.insert(_make_invocation("fs"))
    await repo.insert(_make_invocation("fs", capability_key="write_file"))

    r = await client.get("/api/v1/resources/mcp_server/fs/invocations")
    assert r.status_code == 200
    body = r.json()
    assert len(body["invocations"]) == 2
    keys = {inv["capability_key"] for inv in body["invocations"]}
    assert keys == {"read_file", "write_file"}


@pytest.mark.asyncio
async def test_invocations_scoped_to_server_name(inv_client: tuple) -> None:
    client, _engine, repo = inv_client
    await repo.insert(_make_invocation("fs"))
    await repo.insert(_make_invocation("other_server"))

    r = await client.get("/api/v1/resources/mcp_server/fs/invocations")
    assert r.status_code == 200
    body = r.json()
    assert len(body["invocations"]) == 1
    assert body["invocations"][0]["capability_key"] == "read_file"


# ---------------------------------------------------------------------------
# Status filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_status_ok(inv_client: tuple) -> None:
    client, _engine, repo = inv_client
    await repo.insert(_make_invocation("fs", status="ok"))
    await repo.insert(_make_invocation("fs", capability_key="write_file", status="error"))
    await repo.insert(_make_invocation("fs", capability_key="other", status="timeout"))

    r = await client.get("/api/v1/resources/mcp_server/fs/invocations?status=ok")
    assert r.status_code == 200
    body = r.json()
    assert len(body["invocations"]) == 1
    assert body["invocations"][0]["status"] == "ok"


@pytest.mark.asyncio
async def test_filter_by_status_error(inv_client: tuple) -> None:
    client, _engine, repo = inv_client
    await repo.insert(_make_invocation("fs", status="ok"))
    await repo.insert(_make_invocation("fs", capability_key="write_file", status="error"))

    r = await client.get("/api/v1/resources/mcp_server/fs/invocations?status=error")
    assert r.status_code == 200
    body = r.json()
    assert len(body["invocations"]) == 1
    assert body["invocations"][0]["status"] == "error"
    assert body["invocations"][0]["error_message"] == "boom"


# ---------------------------------------------------------------------------
# Limit filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_limit_filter(inv_client: tuple) -> None:
    client, _engine, repo = inv_client
    for i in range(10):
        await repo.insert(_make_invocation("fs", capability_key=f"tool_{i}"))

    r = await client.get("/api/v1/resources/mcp_server/fs/invocations?limit=3")
    assert r.status_code == 200
    assert len(r.json()["invocations"]) == 3


@pytest.mark.asyncio
async def test_limit_min_boundary(inv_client: tuple) -> None:
    client, *_ = inv_client
    r = await client.get("/api/v1/resources/mcp_server/fs/invocations?limit=0")
    # limit must be ge=1 → FastAPI validation returns 422
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_limit_max_boundary(inv_client: tuple) -> None:
    client, *_ = inv_client
    r = await client.get("/api/v1/resources/mcp_server/fs/invocations?limit=501")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Since filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_since_filter(inv_client: tuple) -> None:
    client, _engine, repo = inv_client
    # Insert one old and one recent invocation
    await repo.insert(_make_invocation("fs", capability_key="old_tool", offset_seconds=3600))
    await repo.insert(_make_invocation("fs", capability_key="recent_tool", offset_seconds=10))

    # Use UTC Z suffix which FastAPI / Python datetime parsing accepts without
    # needing to URL-encode the '+' in '+00:00'.
    cutoff = (datetime.now(tz=UTC) - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = await client.get(f"/api/v1/resources/mcp_server/fs/invocations?since={cutoff}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["invocations"]) == 1
    assert body["invocations"][0]["capability_key"] == "recent_tool"


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="001-mcp-gateway", scenario="invocation log records calls without arguments"
)
@pytest.mark.asyncio
async def test_invocation_response_shape(inv_client: tuple) -> None:
    client, _engine, repo = inv_client
    await repo.insert(_make_invocation("fs", capability_key="read_file", session_id="sess-123"))
    r = await client.get("/api/v1/resources/mcp_server/fs/invocations")
    assert r.status_code == 200
    inv = r.json()["invocations"][0]
    assert "timestamp" in inv
    assert inv["capability_type"] == "tool"
    assert inv["capability_key"] == "read_file"
    assert isinstance(inv["duration_ms"], int)
    assert inv["status"] == "ok"
    assert inv["session_id"] == "sess-123"
    assert inv["error_message"] is None
