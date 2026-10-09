"""The memory hub is vault content: a sync round carries it to the other
machine like any other vault file (spec memory "Keep every agent's memories in
a hub in the vault")."""

from __future__ import annotations

import pytest

from coffer.domain.memory.hub import HubEntry, Origin, entry_id
from coffer.domain.sync.rounds import RoundStatus
from coffer.infrastructure.memory.hub_store import HubChanges, HubStore

from .machines import Machine


def _entry(project: str) -> HubEntry:
    origin = Origin(machine="mac", agent="claude_code", source="projects/x/memory/testing")
    return HubEntry(
        id=entry_id(origin.machine, origin.agent, origin.source),
        origin=origin,
        project=project,
        type="feedback",
        title="Integration tests hit a real database",
        description="Never mock the DB in integration tests.",
        body="A mocked run hid a broken migration in `<repo>/db`.",
        created_at="2026-10-09T06:00:00Z",
        updated_at="2026-10-09T06:00:00Z",
    )


@pytest.mark.acceptance(spec="memory", scenario="the hub travels with vault sync")
def test_a_hub_entry_published_on_one_machine_arrives_on_the_other(
    pair: tuple[Machine, Machine],
) -> None:
    mac, mini = pair
    entry = _entry("github.com/acme/payments")
    published = HubStore(lambda: mac.writer).apply(
        HubChanges(upserts=[entry]), "Published 1 memory", "system:memory-sync-worker"
    )
    assert published is not None

    assert mac.round().status is RoundStatus.PUSHED
    assert mini.round().status in {RoundStatus.PULLED, RoundStatus.PULLED_AND_PUSHED}

    path = f"memory/{entry.path}"
    assert mini.disk(path) == mac.disk(path)
    assert HubStore(lambda: mini.writer).entries() == {entry.id: entry}
