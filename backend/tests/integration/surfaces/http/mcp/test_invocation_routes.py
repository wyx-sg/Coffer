"""Integration tests for MCP invocation log query route."""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.capability import (
    BUILTIN_SERVER_UID,
    MCPInvocation,
)
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.mcp.dependencies import get_invocation_repo
from coffer.surfaces.http.mcp.invocation_routes import (
    aggregate_router as invocation_aggregate_router,
)
from coffer.surfaces.http.mcp.invocation_routes import router as invocation_router
from tests.support.vault_stores import make_resource_repo

#: The uid of a server since deleted: its rows stay in the log, under the uid.
_GONE_UID = "0123456789abcdef0123456789abcdef"
_STDIO = {"transport": {"type": "stdio", "command": "/bin/true", "args": []}}


def _make_invocation(
    resource_uid: str,
    capability_key: str = "read_file",
    status: str = "ok",
    duration_ms: int = 10,
    offset_seconds: int = 0,
    session_id: str | None = None,
    agent_uid: str | None = None,
) -> MCPInvocation:
    return MCPInvocation(
        id=None,
        timestamp=datetime.now(tz=UTC) - timedelta(seconds=offset_seconds),
        resource_uid=resource_uid,
        capability_type="tool",
        capability_key=capability_key,
        duration_ms=duration_ms,
        status=status,  # type: ignore[arg-type]
        error_message="boom" if status == "error" else None,
        session_id=session_id,
        agent_uid=agent_uid,
    )


async def _build_app(
    tmp_path: Path,
) -> tuple[FastAPI, Any, MCPInvocationRepo, ResourceService, dict[str, str]]:
    """Build a minimal FastAPI app wired for invocation route tests.

    Registers two real servers because the routes now address by uid and
    resolve the label back at read time — there is nothing for a test to assert
    about ``resource_name`` unless the resources actually exist. ``uids`` maps
    each server's name to its uid, since a uid is minted and cannot be spelled
    by the test.
    """
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    inv_repo = MCPInvocationRepo(sm)
    rsvc = ResourceService(
        kinds={
            "mcp_server": Kind(
                name="mcp_server",
                display_name="MCP Server",
                config_schema=MCPServerConfig,
            )
        },
        repo=make_resource_repo(),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
    )
    uids = {
        name: (await rsvc.register(kind="mcp_server", name=name, config=_STDIO, actor="test")).uid
        for name in ("fs", "jira", "other_server")
    }

    set_active_token("test-token")

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(invocation_router)
    app.include_router(invocation_aggregate_router)
    app.dependency_overrides[get_invocation_repo] = lambda: inv_repo
    app.dependency_overrides[get_resource_service] = lambda: rsvc

    return app, engine, inv_repo, rsvc, uids


@pytest.fixture
async def inv_client(tmp_path: Path):
    """Yield (client, engine, inv_repo, rsvc, uids)."""
    app, engine, inv_repo, rsvc, uids = await _build_app(tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Coffer-Token": "test-token"},
    ) as client:
        yield client, engine, inv_repo, rsvc, uids

    with suppress(BaseException):
        await engine.dispose()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_invocations_list(inv_client: tuple) -> None:
    client, _engine, _repo, _rsvc, uids = inv_client
    r = await client.get(f"/api/v1/resources/mcp_server/{uids['fs']}/invocations")
    assert r.status_code == 200, r.text
    assert r.json() == {"invocations": [], "next_cursor": None, "total": 0}


@pytest.mark.asyncio
async def test_per_server_invocations_404_for_unknown_uid(inv_client: tuple) -> None:
    """ "No such server" and "this server has made no calls" are different
    answers, and the resource page needs to tell them apart."""
    client, *_ = inv_client
    r = await client.get("/api/v1/resources/mcp_server/nosuchuid/invocations")
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_invocations_requires_auth(tmp_path: Path) -> None:
    app, engine, _repo, _rsvc, uids = await _build_app(tmp_path)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "bad-token"},
        ) as client:
            r = await client.get(f"/api/v1/resources/mcp_server/{uids['fs']}/invocations")
            assert r.status_code == 401
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Basic retrieval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invocations_returned_after_insert(inv_client: tuple) -> None:
    client, _engine, repo, _rsvc, uids = inv_client
    await repo.insert(_make_invocation(uids["fs"]))
    await repo.insert(_make_invocation(uids["fs"], capability_key="write_file"))

    r = await client.get(f"/api/v1/resources/mcp_server/{uids['fs']}/invocations")
    assert r.status_code == 200
    body = r.json()
    assert len(body["invocations"]) == 2
    keys = {inv["capability_key"] for inv in body["invocations"]}
    assert keys == {"read_file", "write_file"}


@pytest.mark.asyncio
async def test_invocations_scoped_to_one_server(inv_client: tuple) -> None:
    client, _engine, repo, _rsvc, uids = inv_client
    await repo.insert(_make_invocation(uids["fs"]))
    await repo.insert(_make_invocation(uids["other_server"]))

    r = await client.get(f"/api/v1/resources/mcp_server/{uids['fs']}/invocations")
    assert r.status_code == 200
    body = r.json()
    assert len(body["invocations"]) == 1
    assert body["invocations"][0]["capability_key"] == "read_file"


# ---------------------------------------------------------------------------
# Status filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_status_ok(inv_client: tuple) -> None:
    client, _engine, repo, _rsvc, uids = inv_client
    fs = uids["fs"]
    await repo.insert(_make_invocation(fs, status="ok"))
    await repo.insert(_make_invocation(fs, capability_key="write_file", status="error"))
    await repo.insert(_make_invocation(fs, capability_key="other", status="timeout"))

    r = await client.get(f"/api/v1/resources/mcp_server/{fs}/invocations?status=ok")
    assert r.status_code == 200
    body = r.json()
    assert len(body["invocations"]) == 1
    assert body["invocations"][0]["status"] == "ok"


@pytest.mark.asyncio
async def test_filter_by_status_error(inv_client: tuple) -> None:
    client, _engine, repo, _rsvc, uids = inv_client
    fs = uids["fs"]
    await repo.insert(_make_invocation(fs, status="ok"))
    await repo.insert(_make_invocation(fs, capability_key="write_file", status="error"))

    r = await client.get(f"/api/v1/resources/mcp_server/{fs}/invocations?status=error")
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
    client, _engine, repo, _rsvc, uids = inv_client
    for i in range(10):
        await repo.insert(_make_invocation(uids["fs"], capability_key=f"tool_{i}"))

    r = await client.get(f"/api/v1/resources/mcp_server/{uids['fs']}/invocations?limit=3")
    assert r.status_code == 200
    assert len(r.json()["invocations"]) == 3


@pytest.mark.asyncio
async def test_limit_min_boundary(inv_client: tuple) -> None:
    client, _engine, _repo, _rsvc, uids = inv_client
    r = await client.get(f"/api/v1/resources/mcp_server/{uids['fs']}/invocations?limit=0")
    # limit must be ge=1 → FastAPI validation returns 422
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_limit_max_boundary(inv_client: tuple) -> None:
    client, _engine, _repo, _rsvc, uids = inv_client
    r = await client.get(f"/api/v1/resources/mcp_server/{uids['fs']}/invocations?limit=501")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Since filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_since_filter(inv_client: tuple) -> None:
    client, _engine, repo, _rsvc, uids = inv_client
    fs = uids["fs"]
    # Insert one old and one recent invocation
    await repo.insert(_make_invocation(fs, capability_key="old_tool", offset_seconds=3600))
    await repo.insert(_make_invocation(fs, capability_key="recent_tool", offset_seconds=10))

    # Use UTC Z suffix which FastAPI / Python datetime parsing accepts without
    # needing to URL-encode the '+' in '+00:00'.
    cutoff = (datetime.now(tz=UTC) - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = await client.get(f"/api/v1/resources/mcp_server/{fs}/invocations?since={cutoff}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["invocations"]) == 1
    assert body["invocations"][0]["capability_key"] == "recent_tool"


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="invocation log records calls without arguments"
)
@pytest.mark.asyncio
async def test_invocation_response_shape(inv_client: tuple) -> None:
    client, _engine, repo, _rsvc, uids = inv_client
    await repo.insert(
        _make_invocation(uids["fs"], capability_key="read_file", session_id="sess-123")
    )
    r = await client.get(f"/api/v1/resources/mcp_server/{uids['fs']}/invocations")
    assert r.status_code == 200
    inv = r.json()["invocations"][0]
    assert "timestamp" in inv
    assert inv["capability_type"] == "tool"
    assert inv["capability_key"] == "read_file"
    assert isinstance(inv["duration_ms"], int)
    assert inv["status"] == "ok"
    assert inv["session_id"] == "sess-123"
    assert inv["error_message"] is None
    # The row id is the log's own, and a session that reported no agent names none.
    [stored] = await repo.query(resource_uid=uids["fs"])
    assert inv["id"] == stored.id
    assert inv["agent_uid"] is None


# ---------------------------------------------------------------------------
# Cross-server timeline (/api/v1/mcp/invocations)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_returns_rows_across_servers(inv_client: tuple) -> None:
    """The Activity page shows one timeline, so the row has to say which server
    it came from — the per-server path no longer supplies that context."""
    client, _engine, repo, _rsvc, uids = inv_client
    await repo.insert(_make_invocation(uids["fs"]))
    await repo.insert(_make_invocation(uids["jira"], capability_key="search_issues"))

    r = await client.get("/api/v1/mcp/invocations")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {inv["resource_uid"] for inv in body["invocations"]} == {uids["fs"], uids["jira"]}
    assert {inv["resource_name"] for inv in body["invocations"]} == {"fs", "jira"}


@pytest.mark.asyncio
async def test_aggregate_requires_auth(tmp_path: Path) -> None:
    app, engine, _repo, _rsvc, _uids = await _build_app(tmp_path)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Coffer-Token": "bad-token"},
        ) as client:
            r = await client.get("/api/v1/mcp/invocations")
            assert r.status_code == 401
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_aggregate_uid_filter_narrows_to_one_server(inv_client: tuple) -> None:
    client, _engine, repo, _rsvc, uids = inv_client
    await repo.insert(_make_invocation(uids["fs"]))
    await repo.insert(_make_invocation(uids["jira"], capability_key="search_issues"))

    r = await client.get(f"/api/v1/mcp/invocations?uid={uids['jira']}")
    assert r.status_code == 200
    [inv] = r.json()["invocations"]
    assert inv["resource_uid"] == uids["jira"]
    assert inv["resource_name"] == "jira"
    assert inv["capability_key"] == "search_issues"


@pytest.mark.asyncio
async def test_aggregate_status_and_limit_filters(inv_client: tuple) -> None:
    client, _engine, repo, _rsvc, uids = inv_client
    await repo.insert(_make_invocation(uids["fs"], status="ok"))
    await repo.insert(_make_invocation(uids["jira"], capability_key="a", status="error"))
    await repo.insert(_make_invocation(uids["jira"], capability_key="b", status="error"))

    r = await client.get("/api/v1/mcp/invocations?status=error")
    assert {inv["resource_name"] for inv in r.json()["invocations"]} == {"jira"}
    assert len(r.json()["invocations"]) == 2

    r = await client.get("/api/v1/mcp/invocations?status=error&limit=1")
    assert len(r.json()["invocations"]) == 1

    assert (await client.get("/api/v1/mcp/invocations?limit=0")).status_code == 422


@pytest.mark.asyncio
async def test_per_server_route_also_carries_resource_name(inv_client: tuple) -> None:
    client, _engine, repo, _rsvc, uids = inv_client
    await repo.insert(_make_invocation(uids["fs"]))

    r = await client.get(f"/api/v1/resources/mcp_server/{uids['fs']}/invocations")
    [inv] = r.json()["invocations"]
    assert inv["resource_uid"] == uids["fs"]
    assert inv["resource_name"] == "fs"


# ---------------------------------------------------------------------------
# Read-time name resolution (ADR identity-is-the-uid-inside-the-file)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rename_carries_the_whole_history_under_the_new_name(inv_client: tuple) -> None:
    """The log is keyed by identity, so a rename leaves one history one
    history — and, because the label is resolved at read time rather than
    stored, every past row reads under the CURRENT name. That is the trade the
    contract spells out, so pin it: nothing here should read "fs" afterwards.
    """
    client, _engine, repo, rsvc, uids = inv_client
    await repo.insert(_make_invocation(uids["fs"], capability_key="before_rename"))
    await rsvc.rename(uids["fs"], "filesystem", actor="test")
    await repo.insert(_make_invocation(uids["fs"], capability_key="after_rename"))

    r = await client.get(f"/api/v1/resources/mcp_server/{uids['fs']}/invocations")
    body = r.json()["invocations"]
    assert {inv["capability_key"] for inv in body} == {"before_rename", "after_rename"}
    assert {inv["resource_name"] for inv in body} == {"filesystem"}


@pytest.mark.asyncio
async def test_builtin_and_deleted_uids_resolve_to_a_null_name(inv_client: tuple) -> None:
    """Two recorded values resolve to no resource: the sentinel Coffer's own
    built-in tools log under, and the uid of a server since deleted. Both must
    still appear on the timeline, with a null name the client falls back from."""
    client, _engine, repo, _rsvc, _uids = inv_client
    await repo.insert(_make_invocation(BUILTIN_SERVER_UID, capability_key="coffer__search"))
    await repo.insert(_make_invocation(_GONE_UID, capability_key="do_thing"))

    r = await client.get("/api/v1/mcp/invocations")
    by_uid = {inv["resource_uid"]: inv for inv in r.json()["invocations"]}
    assert by_uid[BUILTIN_SERVER_UID]["resource_name"] is None
    assert by_uid[_GONE_UID]["resource_name"] is None


@pytest.mark.asyncio
async def test_aggregate_filter_accepts_the_builtin_sentinel(inv_client: tuple) -> None:
    """``?uid=`` takes the value the rows were written under, so the reserved
    forms are filterable too — a name filter never could be."""
    client, _engine, repo, _rsvc, uids = inv_client
    await repo.insert(_make_invocation(uids["fs"]))
    await repo.insert(_make_invocation(BUILTIN_SERVER_UID, capability_key="coffer__search"))

    r = await client.get(f"/api/v1/mcp/invocations?uid={BUILTIN_SERVER_UID}")
    [inv] = r.json()["invocations"]
    assert inv["capability_key"] == "coffer__search"
    assert inv["resource_name"] is None


@pytest.mark.asyncio
async def test_name_resolution_is_one_lookup_for_the_whole_page(
    inv_client: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A page of rows costs ONE resource query, not one per row. Left
    unbounded that is 500 lookups of the same handful of servers on the
    Activity page's largest page size."""
    client, _engine, repo, rsvc, uids = inv_client
    for i in range(12):
        await repo.insert(_make_invocation(uids["fs"], capability_key=f"tool_{i}"))
        await repo.insert(_make_invocation(uids["jira"], capability_key=f"jira_{i}"))

    calls: list[Any] = []
    real_list = rsvc.list

    async def _counting_list(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return await real_list(*args, **kwargs)

    monkeypatch.setattr(rsvc, "list", _counting_list)

    r = await client.get("/api/v1/mcp/invocations")
    assert len(r.json()["invocations"]) == 24
    assert len(calls) == 1, f"expected one resource lookup for the page, got {len(calls)}"


# ---------------------------------------------------------------------------
# Calling agent (spec mcp-gateway "Record invocations without content")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_uid_is_carried_and_filters_both_routes(inv_client: tuple) -> None:
    client, _engine, repo, _rsvc, uids = inv_client
    fs = uids["fs"]
    await repo.insert(_make_invocation(fs, capability_key="mine", agent_uid="agent-a"))
    await repo.insert(_make_invocation(fs, capability_key="theirs", agent_uid="agent-b"))
    await repo.insert(_make_invocation(fs, capability_key="nobody"))
    await repo.insert(_make_invocation(uids["jira"], capability_key="jira", agent_uid="agent-a"))

    everything = (await client.get("/api/v1/mcp/invocations")).json()
    by_key = {inv["capability_key"]: inv["agent_uid"] for inv in everything["invocations"]}
    assert by_key == {"mine": "agent-a", "theirs": "agent-b", "nobody": None, "jira": "agent-a"}

    agg = (await client.get("/api/v1/mcp/invocations?agent_uid=agent-a")).json()
    assert {inv["capability_key"] for inv in agg["invocations"]} == {"mine", "jira"}
    assert agg["total"] == 2

    per_server = await client.get(
        f"/api/v1/resources/mcp_server/{fs}/invocations?agent_uid=agent-a"
    )
    assert [inv["capability_key"] for inv in per_server.json()["invocations"]] == ["mine"]
    assert per_server.json()["total"] == 1


@pytest.mark.asyncio
async def test_a_cursor_is_bound_to_the_agent_filter(inv_client: tuple) -> None:
    client, _engine, repo, _rsvc, uids = inv_client
    for i in range(3):
        await repo.insert(
            _make_invocation(uids["fs"], capability_key=f"t{i}", offset_seconds=i, agent_uid="a")
        )

    issued = (await client.get("/api/v1/mcp/invocations?limit=1")).json()["next_cursor"]
    assert issued is not None
    refused = await client.get(
        "/api/v1/mcp/invocations", params={"limit": 1, "agent_uid": "a", "cursor": issued}
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["error"]["code"] == "CURSOR_INVALID"

    bound = (await client.get("/api/v1/mcp/invocations?limit=1&agent_uid=a")).json()
    follow = await client.get(
        "/api/v1/mcp/invocations",
        params={"limit": 1, "agent_uid": "a", "cursor": bound["next_cursor"]},
    )
    assert follow.status_code == 200, follow.text
    assert [inv["capability_key"] for inv in follow.json()["invocations"]] == ["t1"]


# ---------------------------------------------------------------------------
# Total (spec resource-framework "Count a log's matching rows beside each page")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_total_counts_every_matching_row_on_every_page(inv_client: tuple) -> None:
    client, _engine, repo, _rsvc, uids = inv_client
    fs = uids["fs"]
    for i in range(5):
        await repo.insert(
            _make_invocation(fs, capability_key=f"err{i}", status="error", offset_seconds=i)
        )
    await repo.insert(_make_invocation(fs, capability_key="fine", status="ok"))
    await repo.insert(_make_invocation(uids["jira"], capability_key="j", status="error"))

    first = (await client.get("/api/v1/mcp/invocations?status=error&limit=2")).json()
    assert len(first["invocations"]) == 2
    assert first["total"] == 6
    second = (
        await client.get(
            "/api/v1/mcp/invocations",
            params={"status": "error", "limit": 2, "cursor": first["next_cursor"]},
        )
    ).json()
    assert len(second["invocations"]) == 2
    assert second["total"] == 6

    per_server = (
        await client.get(f"/api/v1/resources/mcp_server/{fs}/invocations?status=error&limit=2")
    ).json()
    assert per_server["total"] == 5
    assert (await client.get("/api/v1/mcp/invocations")).json()["total"] == 7


# ---------------------------------------------------------------------------
# Free-text search is the database's
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_q_matches_the_tool_the_error_and_the_servers_current_name(
    inv_client: tuple,
) -> None:
    client, _engine, repo, _rsvc, uids = inv_client
    await repo.insert(_make_invocation(uids["fs"], capability_key="read_file", offset_seconds=30))
    await repo.insert(_make_invocation(uids["fs"], capability_key="write_file", offset_seconds=20))
    await repo.insert(
        _make_invocation(uids["jira"], capability_key="search", status="error", offset_seconds=10)
    )

    by_tool = (await client.get("/api/v1/mcp/invocations", params={"q": "WRITE"})).json()
    by_error = (await client.get("/api/v1/mcp/invocations", params={"q": "boom"})).json()
    by_server = (await client.get("/api/v1/mcp/invocations", params={"q": "jira"})).json()
    paged = (await client.get("/api/v1/mcp/invocations", params={"q": "file", "limit": 1})).json()

    assert [i["capability_key"] for i in by_tool["invocations"]] == ["write_file"]
    assert [i["capability_key"] for i in by_error["invocations"]] == ["search"]
    assert [i["capability_key"] for i in by_server["invocations"]] == ["search"]
    assert by_server["total"] == 1
    assert paged["total"] == 2 and paged["next_cursor"] is not None
    # The cursor belongs to the query it was issued for.
    other = await client.get(
        "/api/v1/mcp/invocations", params={"q": "jira", "limit": 1, "cursor": paged["next_cursor"]}
    )
    assert other.status_code == 400
