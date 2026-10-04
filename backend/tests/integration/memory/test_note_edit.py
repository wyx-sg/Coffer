"""``PUT /api/v1/memory/partitions/{uid}/notes/{slug}`` (spec memory "Edit a
memory in the web UI or on disk").

The whole app on a fake home with one distilled partition. A save replaces the
body and keeps every frontmatter key; a save over a note that changed since is
refused with the note as it is now and leaves the file alone.
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


@pytest.mark.acceptance(
    spec="memory", scenario="a save replaces the body and keeps the frontmatter"
)
def test_a_save_replaces_the_body_and_keeps_the_frontmatter(client, partition: str) -> None:  # noqa: F811
    before = client.get(_url(partition)).json()
    assert before["fingerprint"]

    saved = client.put(
        _url(partition),
        json={
            "body": "Use `uv sync --frozen`, always.",
            "expected_fingerprint": before["fingerprint"],
        },
    )

    assert saved.status_code == 200, saved.text
    after = saved.json()
    assert after["body"] == "Use `uv sync --frozen`, always.\n"
    for key in ("title", "description", "type", "origins", "created_at", "search_terms"):
        assert after[key] == before[key]
    assert after["updated_at"] and after["updated_at"] != before["updated_at"]
    assert after["fingerprint"] != before["fingerprint"]
    # What the next read says, and what is on disk.
    assert client.get(_url(partition)).json() == after
    note = memory_store.read_note("coffer", _SLUG)
    assert note.body == "Use `uv sync --frozen`, always.\n"
    assert note.origins and note.title == before["title"]

    (event,) = [
        e
        for e in client.get("/api/v1/audit").json()["entries"]
        if e["event_type"] == "memory_note_edited"
    ]
    assert event["actor"] == "user"
    assert event["details"] == {"partition": "coffer", "note": _SLUG}


@pytest.mark.acceptance(
    spec="memory", scenario="a save over a note that changed is refused with the current text"
)
def test_a_save_over_a_note_that_changed_is_refused_with_the_current_text(
    client,  # noqa: F811
    partition: str,
) -> None:
    loaded = client.get(_url(partition)).json()
    # A distil pass (or the person's own editor) rewrites the file meanwhile.
    path = memory_paths.note_path("coffer", _SLUG)
    rewritten = path.read_text(encoding="utf-8").replace("uv sync", "uv lock")
    path.write_text(rewritten, encoding="utf-8")

    refused = client.put(
        _url(partition),
        json={"body": "my text", "expected_fingerprint": loaded["fingerprint"]},
    )

    assert refused.status_code == 409, refused.text
    envelope = refused.json()["error"]
    assert envelope["code"] == "MEMORY_NOTE_CONFLICT"
    error = envelope["details"]
    assert error["saved"] is False
    assert "uv lock" in error["current_body"]
    assert path.read_text(encoding="utf-8") == rewritten
    current = client.get(_url(partition)).json()
    assert error["current_fingerprint"] == current["fingerprint"]
    assert not [
        e
        for e in client.get("/api/v1/audit").json()["entries"]
        if e["event_type"] == "memory_note_edited"
    ]

    # Saving the user's text again needs the new fingerprint.
    again = client.put(
        _url(partition),
        json={"body": "my text", "expected_fingerprint": error["current_fingerprint"]},
    )
    assert again.status_code == 200, again.text
    assert again.json()["body"] == "my text\n"


def test_a_save_names_a_note_that_exists_and_a_safe_slug(client, partition: str) -> None:  # noqa: F811
    body = {"body": "x", "expected_fingerprint": "f"}
    assert client.put(_url(partition, "no-such-note"), json=body).status_code == 404
    assert client.put(_url(partition, ".hidden"), json=body).status_code == 400
    assert (
        client.put(_url(partition), json={"body": "", "expected_fingerprint": "f"}).status_code
        == 422
    )
