"""A second speech-to-text default is refused outside the dedicated route.

Spec provider-switching "Keep an independent speech-to-text default": the
flag is moved only by ``POST /providers/{uid}/transcribe-default``, which clears
the old holder first. Every other write that would leave two connections flagged
— the kind-agnostic resource PATCH and POST — answers a clean 409 naming the
holder.
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


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a second speech-to-text default outside the dedicated route is refused",
)
def test_a_second_transcribe_default_is_refused_with_a_409(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with _client(tmp_path, monkeypatch) as c:
        first = _new(c, "first")
        second = _new(c, "second")
        assert c.post(f"/api/v1/providers/{first}/transcribe-default").status_code == 200

        row = c.get(f"/api/v1/resources/{second}").json()
        r = c.patch(
            f"/api/v1/resources/{second}",
            json={"config": {**row["config"], "transcribe_default": True}},
        )

        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "PROVIDER_TRANSCRIBE_DEFAULT_TAKEN"
        assert "first" in r.json()["error"]["message"]
        assert c.get(f"/api/v1/providers/{first}").json()["transcribe_default"] is True
        assert c.get(f"/api/v1/providers/{second}").json()["transcribe_default"] is False
