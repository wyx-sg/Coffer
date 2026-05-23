"""Tests for the mem0 adapter (`Mem0MemoryStore`).

mem0 itself is stubbed via a fake `mem0` module injected into `sys.modules`,
so these run with no network and no LLM — they exercise the adapter's own
logic: result parsing and the "engine stored nothing" rejection path.
"""

from __future__ import annotations

import sys
import types
from typing import ClassVar

import pytest

from coffer.domain.errors import MemoryRejected
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.infrastructure.memory.mem0_store import (
    Mem0MemoryStore,
    _extract_id,
    _extract_list,
    _payload_to_record,
)


class _FakeClient:
    """Stand-in for a mem0 `Memory` client instance."""

    def __init__(self) -> None:
        # What `add` returns — tests mutate this to drive behaviour.
        self.add_return: object = {"results": [{"id": "m-1", "memory": "stored"}]}

    def add(self, text: str, user_id: str | None = None, metadata: object = None) -> object:
        return self.add_return


class _FakeMemory:
    """Stand-in for the `mem0.Memory` class."""

    instances: ClassVar[list[_FakeClient]] = []

    @classmethod
    def from_config(cls, config: object) -> _FakeClient:
        client = _FakeClient()
        cls.instances.append(client)
        return client


@pytest.fixture
def fake_mem0(monkeypatch: pytest.MonkeyPatch) -> type[_FakeMemory]:
    _FakeMemory.instances = []
    module = types.ModuleType("mem0")
    module.Memory = _FakeMemory  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mem0", module)
    return _FakeMemory


async def _open_store(tmp_path, monkeypatch) -> Mem0MemoryStore:
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "mem"))
    store = Mem0MemoryStore()
    await store.open("s1", MemoryStoreConfig())
    return store


async def test_add_returns_record_when_engine_stores(fake_mem0, tmp_path, monkeypatch):
    store = await _open_store(tmp_path, monkeypatch)
    record = await store.add("s1", "the user prefers tabs over spaces", "agent")
    assert record.id == "m-1"
    assert record.text == "the user prefers tabs over spaces"
    assert record.actor == "agent"


async def test_add_rejects_when_engine_stores_nothing(fake_mem0, tmp_path, monkeypatch):
    """mem0's LLM may decide not to store anything — the adapter must reject
    rather than mint a phantom id that desyncs the memory_records table."""
    store = await _open_store(tmp_path, monkeypatch)
    fake_mem0.instances[0].add_return = {"results": []}
    with pytest.raises(MemoryRejected) as exc:
        await store.add("s1", "a duplicate fact", "agent")
    assert exc.value.reason == "not_stored"


async def test_add_rejects_when_engine_returns_empty_dict(fake_mem0, tmp_path, monkeypatch):
    store = await _open_store(tmp_path, monkeypatch)
    fake_mem0.instances[0].add_return = {}
    with pytest.raises(MemoryRejected):
        await store.add("s1", "another fact", "agent")


def test_extract_id_handles_mem0_shapes():
    assert _extract_id({"id": "x"}) == "x"
    assert _extract_id({"results": [{"id": "y"}]}) == "y"
    assert _extract_id({"results": []}) is None
    assert _extract_id({}) is None
    assert _extract_id([]) is None


def test_extract_list_handles_mem0_shapes():
    assert _extract_list([{"id": "a"}]) == [{"id": "a"}]
    assert _extract_list({"results": [{"id": "b"}]}) == [{"id": "b"}]
    assert _extract_list({"id": "c"}) == [{"id": "c"}]
    assert _extract_list(None) == []


def test_payload_to_record_maps_fields():
    rec = _payload_to_record(
        "s1",
        {"id": "m9", "memory": "fact", "metadata": {"actor": "user"}},
    )
    assert rec.id == "m9"
    assert rec.store_name == "s1"
    assert rec.text == "fact"
    assert rec.actor == "user"


# ---------------------------------------------------------------------------
# TEST26-005 — Cold paths: when mem0's client raises mid-call, the adapter
# must translate to the right domain outcome (False / MemoryNotFound / []).
# ---------------------------------------------------------------------------


class _RaisingClient:
    """Drives every mem0 method to raise so the adapter's error
    translation paths are exercised."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def add(self, *args, **kwargs):
        # add is not exercised here; the existing tests cover its happy +
        # rejection paths. Default to a benign payload so a future test
        # mixing add+other calls doesn't unexpectedly explode.
        return {"results": [{"id": "x", "memory": "m"}]}

    def get(self, _memory_id):  # type: ignore[no-untyped-def]
        raise self._exc

    def get_all(self, *args, **kwargs):
        raise self._exc

    def update(self, *args, **kwargs):
        raise self._exc

    def delete(self, *args, **kwargs):
        raise self._exc

    def delete_all(self, *args, **kwargs):
        raise self._exc

    def search(self, *args, **kwargs):
        raise self._exc


class _RaisingMemory:
    """``mem0.Memory`` substitute that yields a ``_RaisingClient``."""

    last_exc: ClassVar[Exception | None] = None

    @classmethod
    def from_config(cls, _config: object):  # type: ignore[no-untyped-def]
        assert cls.last_exc is not None
        return _RaisingClient(cls.last_exc)


@pytest.fixture
def raising_mem0(monkeypatch: pytest.MonkeyPatch):
    def _install(exc: Exception) -> type[_RaisingMemory]:
        _RaisingMemory.last_exc = exc
        module = types.ModuleType("mem0")
        module.Memory = _RaisingMemory  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "mem0", module)
        return _RaisingMemory

    return _install


async def _open_raising(raising_mem0, tmp_path, monkeypatch, exc: Exception) -> Mem0MemoryStore:
    raising_mem0(exc)
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "mem"))
    store = Mem0MemoryStore()
    await store.open("s1", MemoryStoreConfig())
    return store


async def test_delete_returns_false_when_client_raises(raising_mem0, tmp_path, monkeypatch):
    """Adapter swallows the mem0 exception and reports the no-op result."""
    store = await _open_raising(raising_mem0, tmp_path, monkeypatch, RuntimeError("nope"))
    assert await store.delete("s1", "m1") is False


async def test_update_raises_memory_not_found_when_client_raises(
    raising_mem0, tmp_path, monkeypatch
):
    """When mem0.update raises, the adapter raises ``MemoryNotFound``."""
    from coffer.domain.errors import MemoryNotFound

    store = await _open_raising(raising_mem0, tmp_path, monkeypatch, RuntimeError("nope"))
    with pytest.raises(MemoryNotFound):
        await store.update("s1", "m1", "new text", actor="user")


async def test_clear_returns_zero_when_client_raises(raising_mem0, tmp_path, monkeypatch):
    """``delete_all`` failures are swallowed; clear() returns 0."""
    store = await _open_raising(raising_mem0, tmp_path, monkeypatch, RuntimeError("nope"))
    assert await store.clear("s1") == 0


async def test_search_propagates_client_error(raising_mem0, tmp_path, monkeypatch):
    """``search`` doesn't have an explicit suppress; a client-side failure
    propagates through the adapter so the caller sees the upstream error
    (the service layer translates it for the response envelope).
    """
    store = await _open_raising(raising_mem0, tmp_path, monkeypatch, RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        await store.search("s1", "q", 5)


async def test_get_returns_none_when_client_raises(raising_mem0, tmp_path, monkeypatch):
    """``get`` translates client errors to ``None`` so the service layer
    can raise its own ``MemoryNotFound`` with full context."""
    store = await _open_raising(raising_mem0, tmp_path, monkeypatch, RuntimeError("nope"))
    assert await store.get("s1", "m1") is None
