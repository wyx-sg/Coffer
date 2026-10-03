"""/api/v1/usage routes against an in-process app over a temp database."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.usage_routes import router as usage_router
from coffer.surfaces.http.usage_wiring import UsageWiring, wire_usage

from .conftest import NOW, FakeClock, FakeNames, FakePrices, record, write_spool


@pytest.fixture
async def wired(sm, tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, UsageWiring]]:  # type: ignore[no-untyped-def]
    wiring = wire_usage(
        sm,
        price_lookup=FakePrices(),
        connection_names=FakeNames({"conn-anthropic": "Anthropic"}),
        spool_dir=tmp_path / "spool",
    )
    # Pin the clocks so "today" and "as of" are deterministic.
    clock = FakeClock(NOW + timedelta(minutes=1))
    wiring.query._clock = clock
    wiring.ingest._tz = wiring.query._tz
    write_spool(tmp_path / "spool", "a.jsonl", [record(1), record(2, model="acme-coder-1")])
    await wiring.ingest.ingest_once()

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(usage_router)
    set_active_token("test-token")
    async with AsyncClient(
        transport=ASGITransport(app),
        base_url="http://127.0.0.1",
        headers={"X-Coffer-Token": "test-token"},
    ) as client:
        yield client, wiring


async def test_summary_route(wired) -> None:  # type: ignore[no-untyped-def]
    client, _ = wired
    r = await client.get("/api/v1/usage/summary", params={"range": "7d", "group_by": "model"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cost_is_estimate"] is True
    assert body["totals"]["requests"] == 2
    assert body["totals"]["unpriced_requests"] == 1
    names = {row["model"]: row["connection_name"] for row in body["rows"]}
    assert names["claude-sonnet-4-6"] == "Anthropic"
    assert body["rows"][0]["agent_types"] == ["claude_code"]
    narrowed = await client.get(
        "/api/v1/usage/summary",
        params={"range": "7d", "agent_type": "codex", "connection_uid": "conn-anthropic"},
    )
    assert narrowed.json()["totals"]["requests"] == 0
    csv_text = await client.get(
        "/api/v1/usage/export.csv", params={"range": "7d", "agent_type": "claude_code"}
    )
    assert len(csv_text.text.splitlines()) == 3  # header + two models
    bad = await client.get(
        "/api/v1/usage/summary", params={"range": "custom", "from": "2026-09-01"}
    )
    assert bad.status_code == 400


async def test_requests_route_pages_by_cursor(wired) -> None:  # type: ignore[no-untyped-def]
    client, _ = wired
    first = (await client.get("/api/v1/usage/requests", params={"limit": 1})).json()
    assert len(first["requests"]) == 1 and first["next_cursor"]
    second = await client.get(
        "/api/v1/usage/requests", params={"limit": 1, "cursor": first["next_cursor"]}
    )
    assert second.json()["next_cursor"] is None
    assert second.json()["requests"][0]["id"] != first["requests"][0]["id"]
    assert (
        await client.get("/api/v1/usage/requests", params={"cursor": "junk"})
    ).status_code == 400


async def test_csv_route(wired) -> None:  # type: ignore[no-untyped-def]
    client, _ = wired
    r = await client.get("/api/v1/usage/export.csv", params={"range": "today", "group_by": "agent"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("agent_uid,agent_type,requests")


async def test_routes_require_the_token(wired) -> None:  # type: ignore[no-untyped-def]
    client, _ = wired
    r = await client.get("/api/v1/usage/summary", headers={"X-Coffer-Token": "wrong"})
    assert r.status_code == 401


async def test_wiring_loops_start_and_stop(wired, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _, wiring = wired
    await wiring.start()
    await wiring.start()  # idempotent
    # Spooled after the first pass: the final drain on stop still ingests it.
    write_spool(tmp_path / "spool", "b.jsonl", [record(3)])
    await wiring.stop()
    assert not (tmp_path / "spool" / "b.jsonl").exists()
