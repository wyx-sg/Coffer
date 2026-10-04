"""The internal engine's settings over the real app (spec internal-engine).

Every test here boots the real ``create_app()`` against a throwaway ``HOME`` and
talks to it over ASGI, so what is asserted is what a surface really gets back:
the route, the service, the vault document
(``state/settings/internal-engine.json``) and the audit trail the composition
root wires together.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from coffer.application.upkeep_schedule import DEFAULT_INTERVALS
from coffer.infrastructure.vault.instance import vault_writer
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-internal-engine"
_PASSES = ("aggregate", "distil")


@pytest.fixture
async def api(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "61310")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "61319")
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


_DOC = "state/settings/internal-engine.json"


def _doc() -> dict:
    """The settings document at HEAD; absent means every default."""
    raw = vault_writer().repo.read("HEAD", _DOC)
    return json.loads(raw) if raw is not None else {}


def _upkeep(doc: dict, name: str) -> dict:
    return (doc.get("upkeep") or {}).get(name) or {}


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="record every settings write with its actor and values",
)
async def test_every_write_is_audited_with_its_actor_and_the_value_after_it(
    api: AsyncClient,
) -> None:
    assert (
        await api.put("/internal-engine-config/upkeep", json={"pass": "distil", "enabled": False})
    ).status_code == 200
    assert (
        await api.put("/internal-engine-config/transcribe-model", json={"model": "hears"})
    ).status_code == 200

    r = await api.get("/audit", params={"event_type": "internal_engine_model_set", "limit": 50})
    assert r.status_code == 200, r.text
    entries = r.json()["entries"]
    assert len(entries) == 2
    assert {e["actor"] for e in entries} == {"tester"}
    details = [e["details"] for e in entries]
    # The value AFTER the write: the switch off, the model stored.
    assert any(d.get("auto_distil_enabled") is False for d in details)
    assert any(d.get("transcribe_model") == "hears" for d in details)


@pytest.mark.acceptance(spec="internal-engine", scenario="read the engine settings")
async def test_the_settings_read_reports_the_stored_values_beside_the_defaults(
    api: AsyncClient,
) -> None:
    assert (
        await api.put("/internal-engine-config/transcribe-model", json={"model": "hears"})
    ).status_code == 200
    assert (
        await api.put(
            "/internal-engine-config/upkeep", json={"pass": "aggregate", "enabled": False}
        )
    ).status_code == 200

    body = await _config(api)

    assert body["transcribe_model"] == "hears"
    assert body["updated_at"]
    assert set(body["upkeep"]) == set(_PASSES)
    assert body["upkeep"]["aggregate"]["enabled"] is False
    assert body["upkeep"]["distil"]["enabled"] is True
    assert "model" not in body and "curate_owner_machine_id" not in body
    assert "model_timeout_s" not in body and "default_model_timeout_s" not in body


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="report a switch and interval for each of the two unattended passes",
)
async def test_the_upkeep_block_names_exactly_the_two_timed_passes(api: AsyncClient) -> None:
    upkeep = (await _config(api))["upkeep"]
    assert set(upkeep) == set(_PASSES)
    for name in _PASSES:
        assert set(upkeep[name]) == {
            "enabled",
            "interval_s",
            "default_interval_s",
            "last_pass_at",
            "next_pass_at",
        }

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

    # The default lives in the worker's module, not in the vault's document.
    doc = _doc()
    for name in _PASSES:
        assert _upkeep(doc, name).get("interval_s") is None


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="refuse an interval below the floor or an unknown pass",
)
async def test_a_floor_breaking_interval_and_an_unknown_pass_are_refused(
    api: AsyncClient,
) -> None:
    await api.put("/internal-engine-config/upkeep", json={"pass": "aggregate", "enabled": False})
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
    assert [upkeep[name]["enabled"] for name in _PASSES] == [True, True]

    # The first write carries only one value; the document it creates still runs both.
    assert (
        await api.put("/internal-engine-config/transcribe-model", json={"model": "hears"})
    ).status_code == 200
    upkeep = (await _config(api))["upkeep"]
    assert [upkeep[name]["enabled"] for name in _PASSES] == [True, True]
    doc = _doc()
    assert doc["transcribe_model"] == "hears"
    assert [_upkeep(doc, name).get("enabled", True) for name in _PASSES] == [True, True]


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

    # Re-marking the connection that already carries the flag changes nothing,
    # although A does not curate the model.
    assert (await api.post(f"/providers/{a}/transcribe-default")).status_code == 200
    assert (await _config(api))["transcribe_model"] == "whisper-x"

    # B curates it: kept.
    assert (await api.post(f"/providers/{b}/transcribe-default")).status_code == 200
    assert (await _config(api))["transcribe_model"] == "whisper-x"

    # C does not: dropped.
    assert (await api.post(f"/providers/{c}/transcribe-default")).status_code == 200
    assert (await _config(api))["transcribe_model"] is None


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="the speech-to-text model changes without touching the rest of the row",
)
async def test_the_transcribe_model_leaves_the_rest_of_the_row_alone(
    api: AsyncClient,
) -> None:
    await api.put("/internal-engine-config/upkeep", json={"pass": "distil", "enabled": False})
    audit_before = len(
        (
            await api.get("/audit", params={"event_type": "internal_engine_model_set", "limit": 50})
        ).json()["entries"]
    )

    r = await api.put("/internal-engine-config/transcribe-model", json={"model": "hears"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transcribe_model"] == "hears"
    assert body["upkeep"]["distil"]["enabled"] is False

    audit_after = len(
        (
            await api.get("/audit", params={"event_type": "internal_engine_model_set", "limit": 50})
        ).json()["entries"]
    )
    assert audit_after == audit_before + 1


async def test_the_call_bound_route_is_gone(api: AsyncClient) -> None:
    assert (await api.put("/internal-engine-config/timeout", json={"seconds": 90})).status_code in (
        404,
        405,
    )


async def test_the_retired_routes_and_keys_are_gone(api: AsyncClient) -> None:
    assert (await api.put("/internal-engine-config", json={"model": "m"})).status_code == 405
    assert (
        await api.put("/internal-engine-config/curation-owner", json={"machine_id": "m"})
    ).status_code == 404
    assert (
        await api.put("/internal-engine-config/upkeep", json={"pass": "curate", "enabled": False})
    ).status_code == 422
    body = await _config(api)
    assert "model" not in body
    assert "curate_owner_machine_id" not in body
    assert set(body["upkeep"]) == set(_PASSES)
