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

from coffer.infrastructure.vault.instance import vault_writer
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-internal-engine"


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


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="record every settings write with its actor and values",
)
async def test_every_write_is_audited_with_its_actor_and_the_value_after_it(
    api: AsyncClient,
) -> None:
    assert (
        await api.put("/internal-engine-config/transcribe-model", json={"model": "hears"})
    ).status_code == 200

    r = await api.get("/audit", params={"event_type": "internal_engine_model_set", "limit": 50})
    assert r.status_code == 200, r.text
    entries = r.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["actor"] == "tester"
    assert entries[0]["details"]["transcribe_model"] == "hears"


@pytest.mark.acceptance(spec="internal-engine", scenario="read the engine settings")
async def test_the_settings_read_reports_the_stored_values(api: AsyncClient) -> None:
    assert (
        await api.put("/internal-engine-config/transcribe-model", json={"model": "hears"})
    ).status_code == 200

    body = await _config(api)

    assert body["transcribe_model"] == "hears"
    assert body["updated_at"]
    assert set(body) == {"transcribe_model", "updated_at"}


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
    assert (
        await api.put("/internal-engine-config/transcribe-model", json={"model": "first"})
    ).status_code == 200
    path = vault_writer().repo.root / _DOC
    doc = json.loads(path.read_text())
    doc["written_by_a_newer_build"] = {"kept": True}
    path.write_text(json.dumps(doc, indent=2) + "\n")
    vault_writer().settle([_DOC])

    r = await api.put("/internal-engine-config/transcribe-model", json={"model": "hears"})
    assert r.status_code == 200, r.text
    assert r.json()["transcribe_model"] == "hears"
    assert _doc()["written_by_a_newer_build"] == {"kept": True}
    entries = (
        await api.get("/audit", params={"event_type": "internal_engine_model_set", "limit": 50})
    ).json()["entries"]
    assert [e["details"]["transcribe_model"] for e in entries][:1] == ["hears"]
    assert len(entries) == 2


async def test_the_call_bound_route_is_gone(api: AsyncClient) -> None:
    assert (await api.put("/internal-engine-config/timeout", json={"seconds": 90})).status_code in (
        404,
        405,
    )


async def test_the_retired_routes_and_keys_are_gone(api: AsyncClient) -> None:
    assert (await api.put("/internal-engine-config", json={"model": "m"})).status_code == 405
    for retired in ("curation-owner", "upkeep"):
        assert (
            await api.put(f"/internal-engine-config/{retired}", json={"pass": "memory_sync"})
        ).status_code in (404, 405)
    body = await _config(api)
    assert "model" not in body
    assert "upkeep" not in body
