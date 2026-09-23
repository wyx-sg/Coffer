"""A second internal-engine default is refused outside the dedicated route.

Spec provider-switching "Keep at most one internal-engine default": the flag is
moved only by ``POST /providers/{uid}/internal-default``, which clears the old
holder first. Every other write that would leave two connections flagged — the
kind-agnostic resource PATCH and POST — answers a clean 409 naming the holder,
never the raw unique-index ``IntegrityError`` a 500 used to leak.
"""

from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-internal-default-refused"


def _client(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "58120")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "58129")
    set_active_token(TOKEN)
    return TestClient(create_app(), headers={"X-Coffer-Token": TOKEN})


def _new(c: TestClient, name: str) -> str:
    r = c.post(
        "/api/v1/providers",
        json={
            "name": name,
            "protocol": "anthropic",
            "base_url": f"https://{name}/anthropic",
            "secret_value": "sk-secret",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["uid"]


def _flag(c: TestClient, uid: str) -> bool:
    return c.get(f"/api/v1/providers/{uid}").json()["internal_default"] is True


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a second internal default outside the dedicated route is refused",
)
def test_a_second_internal_default_is_refused_with_a_409(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with _client(tmp_path, monkeypatch) as c:
        first = _new(c, "first")
        second = _new(c, "second")
        assert c.post(f"/api/v1/providers/{first}/internal-default").status_code == 200

        # The generic PATCH, flagging a second connection.
        row = c.get(f"/api/v1/resources/{second}").json()
        config = {**row["config"], "internal_default": True}
        r = c.patch(f"/api/v1/resources/{second}", json={"config": config})

        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "PROVIDER_INTERNAL_DEFAULT_TAKEN"
        assert "first" in r.json()["error"]["message"]
        # Nothing moved: the holder keeps it, the refused row stays clear.
        assert _flag(c, first) is True
        assert _flag(c, second) is False

        # The generic POST, creating a connection that is already flagged.
        created = c.post(
            "/api/v1/resources",
            json={
                "kind": "provider",
                "name": "third",
                "config": {
                    # Keyless, so nothing but the flag stands in its way.
                    "protocol": "ollama",
                    "base_url": "http://localhost:11434",
                    "internal_default": True,
                },
            },
        )
        assert created.status_code == 409, created.text
        assert created.json()["error"]["code"] == "PROVIDER_INTERNAL_DEFAULT_TAKEN"
        names = [
            row["name"]
            for row in c.get("/api/v1/resources", params={"kind": "provider"}).json()["resources"]
        ]
        assert "third" not in names

        # An edit to the holder itself that keeps its flag is not a second one.
        holder = c.get(f"/api/v1/resources/{first}").json()
        kept = c.patch(
            f"/api/v1/resources/{first}",
            json={"config": {**holder["config"], "base_url": "https://first/v2"}},
        )
        assert kept.status_code == 200, kept.text
        assert kept.json()["config"]["internal_default"] is True

        # The dedicated route still moves the flag.
        moved = c.post(f"/api/v1/providers/{second}/internal-default")
        assert moved.status_code == 200, moved.text
        assert _flag(c, second) is True
        assert _flag(c, first) is False
    set_active_token(None)
