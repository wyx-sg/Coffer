"""MemoryStore port + MemoryHit value object."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.record import Actor, MemoryRecord


@dataclass(frozen=True)
class MemoryHit:
    """One ranked memory returned from `MemoryStore.search`."""

    id: str
    text: str
    score: float
    created_at: datetime


@runtime_checkable
class MemoryStore(Protocol):
    """Port for write + retrieve. Single point of mem0 coupling."""

    async def open(self, store_name: str, config: MemoryStoreConfig) -> None: ...

    async def add(self, store_name: str, text: str, actor: Actor) -> MemoryRecord: ...

    async def get(self, store_name: str, memory_id: str) -> MemoryRecord | None: ...

    async def list(self, store_name: str, *, limit: int, offset: int) -> Sequence[MemoryRecord]: ...

    async def update(
        self,
        store_name: str,
        memory_id: str,
        new_text: str,
        *,
        actor: Actor,
    ) -> MemoryRecord:
        """Persist a new text for ``memory_id`` and stamp ``actor``.

        mem0 itself does not retain the actor on update; the adapter
        records the caller-supplied actor on the returned ``MemoryRecord``
        so audit/persistence stay accurate (CODE26-023). Implementations
        should also return mem0's *canonical* post-update text rather than
        the input, since mem0 may rewrite/condense the fact (CODE26-022).
        """
        ...

    async def delete(self, store_name: str, memory_id: str) -> bool: ...

    async def clear(self, store_name: str) -> int: ...

    async def search(self, store_name: str, query: str, top_k: int) -> Sequence[MemoryHit]: ...

    async def drop(self, store_name: str) -> None: ...

    async def close(self) -> None: ...
