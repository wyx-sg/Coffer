"""``DELETE /api/v1/memory/partitions/{uid}/notes/{slug}`` (spec memory "Delete a memory by hand").

The whole app on a fake home with one distilled partition. A note is deleted by
hand and not recreated; no route writes a note's body (spec memory "Edit a
memory in the person's own editor").
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.memory import paths as memory_paths
from coffer.infrastructure.memory import store as memory_store
from tests.integration.surfaces.http.test_memory_routes import (  # noqa: F401
    _default_files,
    _partition_uid,
    _register_agent,
    _repository,
    _seed,
    _sync,
    client,
)

_SLUG = "python-lockfile"


def _url(uid: str, slug: str = _SLUG) -> str:
    return f"/api/v1/memory/partitions/{uid}/notes/{slug}"


@pytest.fixture
def partition(client, tmp_path: pathlib.Path) -> str:  # noqa: F811
    _register_agent(client)
    _seed(tmp_path, _repository(tmp_path), _default_files())
    _sync(client)
    return _partition_uid(client, "coffer")


def test_no_route_writes_a_notes_body(client, partition: str) -> None:  # noqa: F811
    refused = client.put(_url(partition), json={"body": "x", "expected_fingerprint": "f"})

    assert refused.status_code == 405
    assert "fingerprint" not in client.get(_url(partition)).json()


@pytest.mark.acceptance(
    spec="memory", scenario="a memory deleted by hand is retired and not recreated"
)
def test_a_memory_deleted_by_hand_is_retired_and_not_recreated(client, partition: str) -> None:  # noqa: F811
    before = memory_store.read_note("coffer", _SLUG)
    assert before.origins

    deleted = client.delete(_url(partition))

    assert deleted.status_code == 204, deleted.text
    assert not memory_paths.note_path("coffer", _SLUG).exists()
    assert client.get(_url(partition)).status_code == 404
    (record,) = [r for r in memory_store.read_retired("coffer") if r.slug == _SLUG]
    assert record.reason == "Deleted by hand"
    assert record.replaced_by == ""
    assert record.retired_at
    assert record.entry_ids == tuple(o.key for o in before.origins)
    assert _SLUG not in memory_store.read_index("coffer")
    retired = client.get(f"/api/v1/memory/partitions/{partition}/retired").json()["retired"]
    assert [r["slug"] for r in retired if r["reason"] == "Deleted by hand"] == [_SLUG]
    (event,) = [
        e
        for e in client.get("/api/v1/audit").json()["entries"]
        if e["event_type"] == "memory_note_deleted"
    ]
    assert event["actor"] == "user"
    assert event["details"] == {"partition": "coffer", "note": _SLUG}

    # The agent's own memory still holds the entries: the next update must not
    # bring the note back.
    _sync(client)
    assert not memory_paths.note_path("coffer", _SLUG).exists()
    assert _SLUG not in [
        n["slug"]
        for n in client.get(f"/api/v1/memory/partitions/{partition}/notes").json()["notes"]
    ]


def test_deleting_a_memory_that_is_not_there_is_a_404(client, partition: str) -> None:  # noqa: F811
    assert client.delete(_url(partition, "no-such-note")).status_code == 404
