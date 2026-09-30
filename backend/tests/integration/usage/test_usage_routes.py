"""/api/v1/usage routes against an in-process app over a temp database."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.usage_routes import router as usage_router
from coffer.surfaces.http.usage_wiring import UsageWiring, wire_usage

from .conftest import NOW, FakeClock, FakeNames, FakePrices, record, write_spool

_LATER = int((NOW + timedelta(hours=2)).timestamp())


class _Reader:
    def __init__(self) -> None:
        self.calls = 0

    async def read(self) -> dict[str, Any] | None:
        self.calls += 1
        return {
            "rateLimits": {
                "primary": {"usedPercent": 64, "windowDurationMins": 300, "resetsAt": _LATER}
            }
        }


@pytest.fixture
async def wired(sm, tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, UsageWiring, _Reader]]:  # type: ignore[no-untyped-def]
    reader = _Reader()
    wiring = wire_usage(
        sm,
        price_lookup=FakePrices(),
        connection_names=FakeNames({"conn-anthropic": "Anthropic"}),
        codex_reader=reader,
        spool_dir=tmp_path / "spool",
    )
    # Pin the clocks so "today" and "as of" are deterministic.
    clock = FakeClock(NOW + timedelta(minutes=1))
    wiring.query._clock = clock
    wiring.quota._clock = clock
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
        yield client, wiring, reader


async def test_summary_route(wired) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = wired
    r = await client.get("/api/v1/usage/summary", params={"range": "7d", "group_by": "model"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cost_is_estimate"] is True
    assert body["totals"]["requests"] == 2
    assert body["totals"]["unpriced_requests"] == 1
    names = {row["model"]: row["connection_name"] for row in body["rows"]}
    assert names["claude-sonnet-4-6"] == "Anthropic"
    bad = await client.get(
        "/api/v1/usage/summary", params={"range": "custom", "from": "2026-09-01"}
    )
    assert bad.status_code == 400


async def test_requests_route_pages_by_cursor(wired) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = wired
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
    client, _, _ = wired
    r = await client.get("/api/v1/usage/export.csv", params={"range": "today", "group_by": "agent"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("agent_uid,agent_type,requests")


async def test_quota_routes(wired) -> None:  # type: ignore[no-untyped-def]
    client, _, reader = wired
    empty = (await client.get("/api/v1/usage/quota")).json()["agents"]
    assert [(a["agent_type"], a["has_value"], a["windows"]) for a in empty] == [
        ("claude_code", False, []),
        ("codex", False, []),
    ]

    refreshed = (await client.post("/api/v1/usage/quota/refresh")).json()
    assert refreshed["refreshed"] is True
    codex = next(a for a in refreshed["agents"] if a["agent_type"] == "codex")
    assert codex["has_value"] is True
    assert codex["windows"][0]["used_percent"] == 64.0
    assert codex["windows"][0]["as_of"].startswith("2026-09-30T12:01")
    again = (await client.post("/api/v1/usage/quota/refresh")).json()
    assert (again["refreshed"], again["reason"]) == (False, "too_soon")
    assert reader.calls == 1

    posted = await client.post(
        "/api/v1/usage/quota/statusline",
        json={"rate_limits": {"five_hour": {"used_percentage": 18, "resets_at": _LATER}}},
    )
    assert posted.json() == {"accepted": True}
    junk = await client.post("/api/v1/usage/quota/statusline", json={"rate_limits": {}})
    assert junk.json() == {"accepted": False}
    claude = next(
        a
        for a in (await client.get("/api/v1/usage/quota")).json()["agents"]
        if a["agent_type"] == "claude_code"
    )
    assert claude["windows"][0]["used_percent"] == 18.0
    assert claude["windows"][0]["source"] == "claude_statusline"


class _Agents:
    """The registry, holding one Claude Code agent at a custom config dir."""

    def __init__(self, config_dir: Path) -> None:
        self._row = type(
            "Row", (), {"config": {"type": "claude_code", "config_dir": str(config_dir)}}
        )

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> list[Any]:
        return [self._row]


@pytest.mark.acceptance(
    spec="provider-switching", scenario="the quota page hands the statusline opt-in to an agent"
)
async def test_claude_codes_empty_row_hands_the_statusline_opt_in_to_an_agent(  # type: ignore[no-untyped-def]
    wired, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coffer.surfaces.http import dependencies

    client, _, _ = wired
    home = tmp_path / "cc-home"
    monkeypatch.setattr(dependencies, "_resource_service", _Agents(home))
    rows = {a["agent_type"]: a for a in (await client.get("/api/v1/usage/quota")).json()["agents"]}

    assert rows["codex"]["handoff"] is None
    prompt = rows["claude_code"]["handoff"]["prompt"]
    # The registered agent's own settings file, the wrapper's exact form, and
    # the diff shown first; nothing about a token or a quota endpoint.
    assert f"{home / 'settings.json'}" in prompt
    assert "coffer usage statusline -- " in prompt
    assert "`coffer usage statusline` alone" in prompt
    assert "show me the diff" in prompt
    assert "oauth" not in prompt.lower() and "token" not in prompt.lower()

    # Once a value is seen, the row has nothing to hand off.
    await client.post(
        "/api/v1/usage/quota/statusline",
        json={"rate_limits": {"five_hour": {"used_percentage": 18, "resets_at": _LATER}}},
    )
    rows = {a["agent_type"]: a for a in (await client.get("/api/v1/usage/quota")).json()["agents"]}
    assert rows["claude_code"]["handoff"] is None


async def test_routes_require_the_token(wired) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = wired
    r = await client.get("/api/v1/usage/quota", headers={"X-Coffer-Token": "wrong"})
    assert r.status_code == 401


async def test_wiring_loops_start_and_stop(wired, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _, wiring, _ = wired
    await wiring.start()
    await wiring.start()  # idempotent
    # Spooled after the first pass: the final drain on stop still ingests it.
    write_spool(tmp_path / "spool", "b.jsonl", [record(3)])
    await wiring.stop()
    assert not (tmp_path / "spool" / "b.jsonl").exists()
