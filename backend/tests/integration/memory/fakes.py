"""In-memory FakeMemoryStore — doesn't need mem0 / ollama / openai."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.record import Actor, MemoryRecord
from coffer.domain.memory.store import MemoryHit, MemoryStore


class FakeMemoryStore(MemoryStore):
    def __init__(self) -> None:
        self._stores: dict[str, dict[str, MemoryRecord]] = {}
        self.add_calls = 0
        self.search_calls = 0
        self.drop_calls = 0
        self.cleared = 0

    async def open(self, store_name: str, config: MemoryStoreConfig) -> None:
        self._stores.setdefault(store_name, {})

    async def add(self, store_name: str, text: str, actor: Actor) -> MemoryRecord:
        self.add_calls += 1
        now = datetime.now(tz=UTC)
        m = MemoryRecord(
            id=uuid.uuid4().hex,
            store_name=store_name,
            text=text,
            actor=actor,
            created_at=now,
            updated_at=now,
        )
        self._stores.setdefault(store_name, {})[m.id] = m
        return m

    async def get(self, store_name: str, memory_id: str) -> MemoryRecord | None:
        return self._stores.get(store_name, {}).get(memory_id)

    async def list(self, store_name: str, *, limit: int, offset: int) -> Sequence[MemoryRecord]:
        return list(self._stores.get(store_name, {}).values())[offset : offset + limit]

    async def update(
        self,
        store_name: str,
        memory_id: str,
        new_text: str,
        *,
        actor: Actor,
    ) -> MemoryRecord:
        # TEST26-004 / CODE26-023: production (``Mem0MemoryStore.update``)
        # stamps the caller-supplied actor onto the returned record (mem0
        # itself doesn't retain actor across updates). The fake mirrors
        # this contract so service-layer tests do not silently drift from
        # production behaviour.
        m = self._stores.get(store_name, {}).get(memory_id)
        if m is None:
            raise KeyError(memory_id)
        updated = MemoryRecord(
            id=m.id,
            store_name=m.store_name,
            text=new_text,
            actor=actor,
            created_at=m.created_at,
            updated_at=datetime.now(tz=UTC),
        )
        self._stores[store_name][memory_id] = updated
        return updated

    async def delete(self, store_name: str, memory_id: str) -> bool:
        s = self._stores.get(store_name, {})
        if memory_id in s:
            del s[memory_id]
            return True
        return False

    async def clear(self, store_name: str) -> int:
        s = self._stores.get(store_name, {})
        n = len(s)
        s.clear()
        self.cleared += n
        return n

    async def search(self, store_name: str, query: str, top_k: int) -> Sequence[MemoryHit]:
        self.search_calls += 1
        ql = query.lower()
        hits: list[MemoryHit] = []
        for m in self._stores.get(store_name, {}).values():
            score = m.text.lower().count(ql) / max(1, len(m.text))
            if score > 0:
                hits.append(
                    MemoryHit(
                        id=m.id,
                        text=m.text,
                        score=score,
                        created_at=m.created_at,
                    )
                )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    async def drop(self, store_name: str) -> None:
        self.drop_calls += 1
        self._stores.pop(store_name, None)

    async def close(self) -> None:
        self._stores.clear()
