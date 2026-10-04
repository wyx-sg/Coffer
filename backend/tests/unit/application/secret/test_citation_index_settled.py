"""``CitationIndex.settled`` always returns: a finished update that was not yet
taken off the pending set once made it spin forever and hung every request
that waited for the index (the secrets list, delete, release)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from coffer.application.secret.citation_index import CitationIndex


class _NoSource:
    async def list_resources(self) -> list[Any]:
        return []

    async def find_resource(self, uid: str) -> Any:
        return None

    def secret_slots(self, resource: Any) -> dict[str, str]:
        return {}


def _index() -> CitationIndex:
    return CitationIndex(_NoSource(), lambda only: {})  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_a_finished_update_still_on_the_pending_set_does_not_hang() -> None:
    index = _index()
    done: asyncio.Task[None] = asyncio.get_running_loop().create_task(asyncio.sleep(0))
    await done
    # Finished, but its done-callback has not taken it off the set yet.
    index._pending.add(done)

    await asyncio.wait_for(index.settled(), timeout=2)

    assert not index._pending


@pytest.mark.asyncio
async def test_an_update_that_never_finishes_is_read_past_within_the_bound() -> None:
    index = _index()
    stuck = asyncio.get_running_loop().create_task(asyncio.Event().wait())
    index._pending.add(stuck)
    started = time.monotonic()
    try:
        await asyncio.wait_for(index.settled(), timeout=10)
    finally:
        stuck.cancel()
    assert time.monotonic() - started < 7
