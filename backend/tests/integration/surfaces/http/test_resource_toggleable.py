"""A kind that declares ``toggleable=False`` refuses enable/disable (spec
resource-framework "Address every resource by an immutable uid through one
kind-agnostic surface").

Boots the full app — the real ``knowledge``, ``memory`` and ``agent`` kinds, as
the composition root registers them — because the claim under test is about
those kinds specifically, not about a fake one. The ``client`` fixture and the
memory helpers come from ``test_memory_routes``, which pins HOME, the database
and both roots under ``tmp_path``, so nothing here touches a real ``~/.coffer``.
"""

from __future__ import annotations

import pytest

from tests.integration.surfaces.http.test_memory_routes import (  # noqa: F401
    _default_files,
    _partition_uid,
    _register_agent,
    _repository,
    _seed,
    _sync,
    client,
)


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a non-toggleable kind refuses to be disabled"
)
def test_a_collection_a_partition_and_an_agent_refuse_to_be_disabled(client, tmp_path) -> None:  # noqa: F811
    r = client.post("/api/v1/knowledge/collections", json={"name": "shopee"})
    assert r.status_code == 201, r.text
    collection_uid = r.json()["uid"]

    agent_uid = _register_agent(client)
    _seed(tmp_path, _repository(tmp_path), _default_files())
    _sync(client)
    partition_uid = _partition_uid(client, "coffer")

    for uid in (collection_uid, partition_uid, agent_uid):
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


def test_a_toggleable_kind_still_reads_toggleable(client) -> None:  # noqa: F811
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
