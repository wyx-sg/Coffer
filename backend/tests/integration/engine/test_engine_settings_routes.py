"""The internal engine's settings over the real app (spec internal-engine).

Every test here boots the real ``create_app()`` against a throwaway ``HOME`` and
SQLite file and talks to it over ASGI, so what is asserted is what a surface
really gets back: the route, the service, the singleton row and the audit trail
the composition root wires together.
"""

from __future__ import annotations

import asyncio
import pathlib
import sqlite3
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from coffer.application.upkeep_schedule import DEFAULT_INTERVALS
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-internal-engine"
_PASSES = ("aggregate", "distil", "curate")


@pytest.fixture
async def api(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "61310")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "61319")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    app = create_app()
    set_active_token(_TOKEN)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app),
            base_url="http://127.0.0.1/api/v1",
            headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "tester"},
        ) as c,
    ):
        yield c
    set_active_token(None)


async def _connection(c: AsyncClient, name: str, *, protocol: str, curated: list[str]) -> str:
    r = await c.post(
        "/providers",
        json={
            "name": name,
            "protocol": protocol,
            "base_url": f"https://{name}.example/v1",
            "secret_value": f"sk-{name}",
            "models": [{"id": m} for m in curated],
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


async def _config(c: AsyncClient) -> dict:
    r = await c.get("/internal-engine-config")
    assert r.status_code == 200, r.text
    return r.json()


def _store_timeout(tmp_path: pathlib.Path, seconds: int) -> None:
    conn = sqlite3.connect(tmp_path / "c.db", timeout=30)
    try:
        conn.execute("UPDATE internal_engine_config SET model_timeout_s = ?", (seconds,))
        conn.commit()
    finally:
        conn.close()


def _row(tmp_path: pathlib.Path) -> dict:
    conn = sqlite3.connect(tmp_path / "c.db")
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM internal_engine_config").fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    return dict(rows[0])


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="record every settings write with its actor and values",
)
async def test_every_write_is_audited_with_its_actor_and_the_value_after_it(
    api: AsyncClient,
) -> None:
    assert (await api.put("/internal-engine-config", json={"model": "  m1  "})).status_code == 200
    assert (
        await api.put("/internal-engine-config/upkeep", json={"pass": "curate", "enabled": False})
    ).status_code == 200
    assert (
        await api.put("/internal-engine-config/timeout", json={"seconds": 120})
    ).status_code == 200
    assert (
        await api.put("/internal-engine-config/transcribe-model", json={"model": "hears"})
    ).status_code == 200

    r = await api.get("/audit", params={"event_type": "internal_engine_model_set", "limit": 50})
    assert r.status_code == 200, r.text
    entries = r.json()["entries"]
    assert len(entries) == 4
    assert {e["actor"] for e in entries} == {"tester"}
    details = [e["details"] for e in entries]
    # The value AFTER the write: the model trimmed, the switch off, the numbers stored.
    assert any(d.get("model") == "m1" for d in details)
    assert any(d.get("auto_curate_enabled") is False for d in details)
    assert any(d.get("model_timeout_s") == 120 for d in details)
    assert any(d.get("transcribe_model") == "hears" for d in details)


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="pair the flagged connection with the chosen engine model",
)
async def test_the_engine_resolves_the_flagged_connection_with_the_chosen_model(
    api: AsyncClient,
) -> None:
    from coffer.surfaces.http.engine_config_composition import internal_engine_connection
    from coffer.surfaces.http.provider_dependencies import get_provider_service

    await _connection(api, "other", protocol="anthropic", curated=["other-model"])
    flagged = await _connection(api, "thinks", protocol="openai", curated=[])
    assert (await api.post(f"/providers/{flagged}/internal-default")).status_code == 200

    engine = internal_engine_connection(get_provider_service())
    # Built once, BEFORE a model is chosen: the answer must follow the row.
    assert await engine.get_default() is None

    await api.put("/internal-engine-config", json={"model": "brain-1"})
    resolved = await engine.get_default()
    assert resolved is not None
    assert resolved.model == "brain-1"
    assert resolved.config.base_url == "https://thinks.example/v1"
    assert resolved.config.protocol.value == "openai"

    await api.put("/internal-engine-config", json={"model": "brain-2"})
    again = await engine.get_default()
    assert again is not None
    assert again.model == "brain-2"


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="report a switch and interval for each of the three passes",
)
async def test_the_upkeep_block_names_exactly_the_three_passes(api: AsyncClient) -> None:
    upkeep = (await _config(api))["upkeep"]
    assert set(upkeep) == set(_PASSES)
    for name in _PASSES:
        assert set(upkeep[name]) == {"enabled", "interval_s", "default_interval_s"}

    r = await api.put(
        "/internal-engine-config/upkeep",
        json={"pass": "distil", "enabled": False, "interval_s": 1800},
    )
    assert r.status_code == 200, r.text
    distil = (await _config(api))["upkeep"]["distil"]
    assert distil["enabled"] is False
    assert distil["interval_s"] == 1800


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="report an unchosen interval beside the default that runs",
)
async def test_an_unchosen_interval_is_reported_beside_its_default(
    api: AsyncClient, tmp_path: pathlib.Path
) -> None:
    await api.put("/internal-engine-config/upkeep", json={"pass": "aggregate", "interval_s": 900})
    assert (await _config(api))["upkeep"]["aggregate"]["interval_s"] == 900

    r = await api.put(
        "/internal-engine-config/upkeep",
        json={"pass": "aggregate", "use_default_interval": True},
    )
    assert r.status_code == 200, r.text
    upkeep = (await _config(api))["upkeep"]
    for name in _PASSES:
        assert upkeep[name]["interval_s"] is None
        assert upkeep[name]["default_interval_s"] == int(DEFAULT_INTERVALS[name])

    # The default lives in the worker's module, not in the vault's row.
    row = _row(tmp_path)
    assert row["aggregate_interval_s"] is None
    assert row["distil_interval_s"] is None
    assert row["curate_interval_s"] is None


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="refuse an interval below the floor or an unknown pass",
)
async def test_a_floor_breaking_interval_and_an_unknown_pass_are_refused(
    api: AsyncClient,
) -> None:
    await api.put("/internal-engine-config/upkeep", json={"pass": "curate", "enabled": False})
    await api.put("/internal-engine-config/upkeep", json={"pass": "distil", "interval_s": 3600})
    before = (await _config(api))["upkeep"]

    r = await api.put("/internal-engine-config/upkeep", json={"pass": "distil", "interval_s": 59})
    assert r.status_code == 422, r.text
    r = await api.put("/internal-engine-config/upkeep", json={"pass": "vacuum", "enabled": True})
    assert r.status_code == 422, r.text

    assert (await _config(api))["upkeep"] == before


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="a fresh vault runs every unattended pass",
)
async def test_a_fresh_vault_ships_every_pass_switched_on(
    api: AsyncClient, tmp_path: pathlib.Path
) -> None:
    upkeep = (await _config(api))["upkeep"]
    assert [upkeep[name]["enabled"] for name in _PASSES] == [True, True, True]

    # The first write carries only a model; the row it creates still runs all three.
    assert (await api.put("/internal-engine-config", json={"model": "m"})).status_code == 200
    upkeep = (await _config(api))["upkeep"]
    assert [upkeep[name]["enabled"] for name in _PASSES] == [True, True, True]
    row = _row(tmp_path)
    assert (
        bool(row["auto_aggregate_enabled"]),
        bool(row["auto_distil_enabled"]),
        bool(row["auto_curate_enabled"]),
    ) == (True, True, True)


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="a stored bound outside the range is clamped by a pass",
)
async def test_a_stored_bound_out_of_range_is_clamped_by_a_pass_and_refused_at_the_route(
    api: AsyncClient, tmp_path: pathlib.Path
) -> None:
    from coffer.application.engine_timeout import (
        MAX_MODEL_TIMEOUT_S,
        MIN_MODEL_TIMEOUT_S,
        resolve_timeout,
    )
    from coffer.surfaces.http.engine_config_composition import read_internal_engine_timeout

    # A row a surface would never have written — an older build, a hand edit.
    assert (await api.put("/internal-engine-config", json={"model": "m"})).status_code == 200
    for stored, runs_under in ((1, MIN_MODEL_TIMEOUT_S), (6000, MAX_MODEL_TIMEOUT_S)):
        # Off the event loop: the app's own background passes write this file
        # through the loop, and a blocking write here would wait on a lock only
        # the loop it is blocking can release.
        await asyncio.to_thread(_store_timeout, tmp_path, stored)
        assert await read_internal_engine_timeout() == stored
        # The reader the passes are wired with, read per call: clamped, not raised.
        assert await resolve_timeout(read_internal_engine_timeout) == float(runs_under)

        r = await api.put("/internal-engine-config/timeout", json={"seconds": stored})
        assert r.status_code == 422, r.text


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="moving the speech-to-text flag drops a model the new connection does not curate",
)
async def test_moving_the_transcribe_flag_drops_an_uncurated_model_only(
    api: AsyncClient,
) -> None:
    a = await _connection(api, "a", protocol="openai", curated=[])
    b = await _connection(api, "b", protocol="openai", curated=["whisper-x"])
    c = await _connection(api, "c", protocol="openai", curated=["something-else"])

    assert (await api.post(f"/providers/{a}/transcribe-default")).status_code == 200
    await api.put("/internal-engine-config/transcribe-model", json={"model": "whisper-x"})
    await api.put("/internal-engine-config", json={"model": "brain"})

    # Re-marking the connection that already carries the flag changes nothing,
    # although A does not curate the model.
    assert (await api.post(f"/providers/{a}/transcribe-default")).status_code == 200
    assert (await _config(api))["transcribe_model"] == "whisper-x"

    # B curates it: kept.
    assert (await api.post(f"/providers/{b}/transcribe-default")).status_code == 200
    assert (await _config(api))["transcribe_model"] == "whisper-x"

    # C does not: dropped. The engine's own model is another row's business.
    assert (await api.post(f"/providers/{c}/transcribe-default")).status_code == 200
    body = await _config(api)
    assert body["transcribe_model"] is None
    assert body["model"] == "brain"


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="the bound and the speech-to-text model change one value at a time",
)
async def test_the_bound_and_the_transcribe_model_leave_the_rest_of_the_row_alone(
    api: AsyncClient,
) -> None:
    await api.put("/internal-engine-config", json={"model": "brain"})
    await api.put("/internal-engine-config/upkeep", json={"pass": "distil", "enabled": False})
    audit_before = len(
        (
            await api.get("/audit", params={"event_type": "internal_engine_model_set", "limit": 50})
        ).json()["entries"]
    )

    r = await api.put("/internal-engine-config/timeout", json={"seconds": 90})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model_timeout_s"] == 90
    assert body["transcribe_model"] is None
    assert body["model"] == "brain"
    assert body["upkeep"]["distil"]["enabled"] is False

    r = await api.put("/internal-engine-config/transcribe-model", json={"model": "hears"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transcribe_model"] == "hears"
    assert body["model_timeout_s"] == 90
    assert body["model"] == "brain"
    assert body["upkeep"]["distil"]["enabled"] is False

    audit_after = len(
        (
            await api.get("/audit", params={"event_type": "internal_engine_model_set", "limit": 50})
        ).json()["entries"]
    )
    assert audit_after == audit_before + 2
