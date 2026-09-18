"""Two appenders, one log: the sequence is assigned by the database.

Separate file from the rest of the repository tests because it is the one that
has to run the two writes against each other rather than one after the other.
Without the correlated ``SELECT MAX(sequence)`` inside the INSERT, both
appenders read the same maximum and the second write lands on a number that is
already taken.
"""

from __future__ import annotations

import asyncio
import uuid

from .conftest import Repos

ACTOR = {"actor_kind": "system", "actor_id": "engine", "source_surface": "daemon"}


async def _seed_run(repos: Repos) -> str:
    run_id = uuid.uuid4().hex
    await repos.runs.create_run(
        run_id=run_id,
        title="Concurrent",
        workdir="/repo",
        machine_id="machine-a",
        template_snapshot={"stages": []},
    )
    return run_id


async def test_concurrent_appends_get_distinct_consecutive_sequences(repos: Repos) -> None:
    run_id = await _seed_run(repos)

    first, second = await asyncio.gather(
        repos.events.append_event(
            event_id=uuid.uuid4().hex,
            run_id=run_id,
            event_type="node.started",
            actor=ACTOR,
        ),
        repos.events.append_event(
            event_id=uuid.uuid4().hex,
            run_id=run_id,
            event_type="node.completed",
            actor=ACTOR,
        ),
    )

    assert {first.sequence, second.sequence} == {1, 2}
    listed = await repos.events.list_events(run_id)
    assert [e.sequence for e in listed] == [1, 2]
    assert {e.id for e in listed} == {first.id, second.id}
