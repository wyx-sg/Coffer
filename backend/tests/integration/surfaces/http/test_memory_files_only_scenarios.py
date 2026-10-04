"""Memory scenarios that follow from notes being plain files and the web UI being
the people's surface (spec memory "Confine reads to registered agents' memory
paths", "Keep notes readable as plain files", "Edit a memory in the web UI or in an
editor", "Manage memory in the web UI").

Reuses the booted app and the seeding helpers of ``test_memory_routes``: HOME, the
database and both roots sit under ``tmp_path``.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.memory import paths as memory_paths
from tests.integration.surfaces.http.test_memory_routes import (  # noqa: F401
    _distilled,
    _partition_uid,
    _register_agent,
    _session_context,
    _sync,
    client,
)


@pytest.mark.acceptance(
    spec="memory", scenario="a path segment that escapes the memory root is refused"
)
def test_a_path_segment_that_escapes_the_memory_root_is_refused(client, tmp_path) -> None:  # noqa: F811
    partition = _distilled(client, tmp_path)
    uid = _partition_uid(client, partition)
    base = f"/api/v1/memory/partitions/{uid}/notes"
    outside = tmp_path / ".coffer" / "derived" / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    before = sorted(p.name for p in memory_paths.memory_root().rglob("*"))

    # ``..`` itself never reaches the route (the router normalises it away);
    # the guard is what stops a hidden or otherwise unsafe segment.
    for slug in (".hidden", "bad:slug"):
        read = client.get(f"{base}/{slug}")
        assert read.status_code == 400, (slug, read.text)
        assert read.json()["error"]["code"] == "MEMORY_UNSAFE_PATH"
        write = client.put(
            f"{base}/{slug}", json={"body": "overwritten", "expected_fingerprint": "x"}
        )
        assert write.status_code == 400, (slug, write.text)
        assert write.json()["error"]["code"] == "MEMORY_UNSAFE_PATH"

    # Nothing outside the partition was read or written.
    assert outside.read_text(encoding="utf-8") == "secret"
    assert sorted(p.name for p in memory_paths.memory_root().rglob("*")) == before


@pytest.mark.acceptance(spec="memory", scenario="an edit made on disk needs no Coffer surface")
def test_an_edit_made_on_disk_needs_no_coffer_surface(client, tmp_path) -> None:  # noqa: F811
    partition = _distilled(client, tmp_path)
    uid = _partition_uid(client, partition)
    note_file = memory_paths.note_path(partition, "python-lockfile")
    text = note_file.read_text(encoding="utf-8")
    assert "uv sync --frozen" in text

    # A person changes the file in their own editor; no Coffer route is called.
    note_file.write_text(
        text.replace("uv sync --frozen", "poetry install --sync").replace(
            "locked with uv", "locked with poetry"
        ),
        encoding="utf-8",
    )

    detail = client.get(f"/api/v1/memory/partitions/{uid}/notes/python-lockfile").json()
    assert "poetry install --sync" in detail["body"]
    assert "uv sync --frozen" not in detail["body"]

    # Delivery composes from the files, so the next session's start carries it.
    agent = client.get("/api/v1/resources", params={"kind": "agent"}).json()["resources"][0]["uid"]
    repository = next(
        p["repository_path"]
        for p in client.get("/api/v1/memory/partitions").json()["partitions"]
        if p["name"] == partition
    )
    assert "locked with poetry" in _session_context(client, agent, repository)

    # The derived tree is disposable: rebuilding it gives back a note without the edit.
    import shutil

    shutil.rmtree(memory_paths.memory_root())
    _sync(client)
    rebuilt = client.get(
        f"/api/v1/memory/partitions/{_partition_uid(client, partition)}/notes/python-lockfile"
    ).json()
    assert "poetry install --sync" not in rebuilt["body"]
    assert "uv sync --frozen" in rebuilt["body"]


@pytest.mark.acceptance(
    spec="memory", scenario="the delivery state of an agent is read on the agent's page"
)
def test_the_delivery_state_of_an_agent_is_read_on_the_agents_page(client, tmp_path) -> None:  # noqa: F811
    connected = _register_agent(client, "claude_code")
    other = _register_agent(client, "codex")
    assert client.post(f"/api/v1/agents/{connected}/coffer-connection").status_code == 200

    first = client.get(f"/api/v1/agents/{connected}/coffer-connection").json()
    second = client.get(f"/api/v1/agents/{other}/coffer-connection").json()

    assert first["state"] == "connected"
    hook = next(p for p in first["parts"] if p["key"] == "memory_hook")
    assert hook["installed"] is True
    assert second["state"] == "disconnected"
    # Installation only: a fire is an audit event, never a field on the state.
    for state in (first, second):
        for part in state["parts"]:
            assert "last_fired" not in part and "last_fired_at" not in part
    assert pathlib.Path(tmp_path).exists()
