"""A kind that declares ``toggleable=False`` refuses enable/disable (spec
resource-framework "Address every resource by an immutable uid through one
kind-agnostic surface").

Boots the full app — the real ``knowledge`` and ``agent`` kinds, as the
composition root registers them — because the claim under test is about those
kinds specifically, not about a fake one. HOME and the database are pinned under
``tmp_path``, so nothing here touches a real ``~/.coffer``.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-toggleable"


@pytest.fixture
def client(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    app = create_app()
    set_active_token(_TOKEN)
    headers = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}
    with TestClient(app, base_url="http://localhost", headers=headers) as c:
        yield c


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a non-toggleable kind refuses to be disabled"
)
def test_a_collection_and_an_agent_refuse_to_be_disabled(client) -> None:  # type: ignore[no-untyped-def]
    r = client.post("/api/v1/knowledge/collections", json={"name": "shopee"})
    assert r.status_code == 201, r.text
    collection_uid = r.json()["uid"]
    r = client.post("/api/v1/agents", json={"type": "claude_code"})
    assert r.status_code == 201, r.text
    agent_uid = r.json()["uid"]

    for uid in (collection_uid, agent_uid):
        for verb in ("disable", "enable"):
            refused = client.post(f"/api/v1/resources/{uid}/{verb}")
            assert refused.status_code == 409, refused.text
            assert refused.json()["error"]["code"] == "RESOURCE_NOT_TOGGLEABLE"

        read = client.get(f"/api/v1/resources/{uid}")
        assert read.status_code == 200, read.text
        assert read.json()["enabled"] is True
        assert read.json()["toggleable"] is False

    # Nothing was recorded, because nothing changed.
    audit = client.get("/api/v1/audit", params={"limit": 500}).json()["entries"]
    assert not any(e["event_type"] in ("resource_enabled", "resource_disabled") for e in audit)


def test_a_toggleable_kind_still_reads_toggleable(client) -> None:  # type: ignore[no-untyped-def]
    """The flag is the kind's answer, so an ordinary kind reads ``True``."""
    created = client.post(
        "/api/v1/resources",
        json={
            "kind": "mcp_server",
            "name": "demo",
            "config": {"transport": {"type": "stdio", "command": "demo-cmd"}},
        },
    )
    assert created.status_code in (200, 201), created.text
    read = client.get(f"/api/v1/resources/{created.json()['uid']}")
    assert read.status_code == 200, read.text
    assert read.json()["toggleable"] is True
