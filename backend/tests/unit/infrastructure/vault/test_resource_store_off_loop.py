"""The file resource store's async reads do their file work off the event loop
(the daemon serves the MCP gateway and HTTP from that loop)."""

from __future__ import annotations

import threading

import pytest

from coffer.infrastructure.vault.resource_store import FileResourceRepo


@pytest.mark.asyncio
async def test_reads_snapshot_in_a_worker_thread() -> None:
    seen: list[int] = []

    def snapshot() -> dict[str, object]:
        seen.append(threading.get_ident())
        return {}

    repo = FileResourceRepo.__new__(FileResourceRepo)  # no vault needed
    repo._snapshot = snapshot  # type: ignore[method-assign]

    assert await repo.find("u") is None
    assert await repo.find_by_name("widget", "w") is None
    assert await repo.list() == []

    assert len(seen) == 3
    assert threading.get_ident() not in seen
