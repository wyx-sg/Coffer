"""mem0 adapter for the `MemoryStore` port.

ONLY file in coffer that imports `mem0`. Import is LAZY (inside methods)
so the module loads even when mem0ai is not installed.

mem0's `user_id` is mapped to the Coffer memory store name.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from coffer.domain.errors import EngineUnavailable, MemoryNotFound, MemoryRejected
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.record import Actor, MemoryRecord
from coffer.domain.memory.store import MemoryHit, MemoryStore
from coffer.infrastructure.memory.paths import memory_store_dir

# Callable resolving a keychain reference into the secret value. Returns
# ``None`` when the reference is absent. Used to thread the openai API key
# into mem0's client at ``open()`` time (CODE26-002). Kept as a structural
# type so this module does not import the keyring adapter directly.
CredentialResolver = Callable[[str], str | None]


class Mem0MemoryStore(MemoryStore):
    """Per-process registry of one mem0 client per memory store."""

    def __init__(self, credential_resolver: CredentialResolver | None = None) -> None:
        self._clients: dict[str, Any] = {}
        self._configs: dict[str, MemoryStoreConfig] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._resolve_credential = credential_resolver

    def _lock(self, store_name: str) -> asyncio.Lock:
        lock = self._locks.get(store_name)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[store_name] = lock
        return lock

    async def open(self, store_name: str, config: MemoryStoreConfig) -> None:
        # CODE26-021: take the per-store lock around the existence check so
        # two concurrent ``open()`` calls don't both build a fresh client and
        # leave one to be garbage collected mid-flight.
        async with self._lock(store_name):
            if store_name in self._clients:
                return
            try:
                # Engine library, no type stubs; may be absent in some envs.
                from mem0 import Memory  # type: ignore
            except ImportError as exc:
                raise EngineUnavailable("mem0", str(exc)) from exc

            store_path = memory_store_dir(store_name)
            store_path.mkdir(parents=True, exist_ok=True)

            # CODE26-002: resolve the openai key from the keychain *before*
            # building mem0's client so the request actually authenticates.
            llm_api_key: str | None = None
            if (
                config.llm_provider == "openai"
                and config.llm_credential_ref
                and self._resolve_credential is not None
            ):
                llm_api_key = self._resolve_credential(config.llm_credential_ref)

            client = await asyncio.to_thread(
                _build_memory_client, Memory, config, store_path, llm_api_key
            )
            self._clients[store_name] = client
            self._configs[store_name] = config

    async def add(self, store_name: str, text: str, actor: Actor) -> MemoryRecord:
        client = self._require(store_name)
        async with self._lock(store_name):
            result = await asyncio.to_thread(
                client.add,
                text,
                user_id=store_name,
                metadata={"actor": actor},
            )
        # mem0's LLM-driven add may store nothing (it decided the text
        # duplicates an existing memory, or is not worth keeping). In that
        # case there is no id to persist — reject rather than mint a phantom
        # id that would desync the memory_records table from mem0.
        memory_id = _extract_id(result)
        if memory_id is None:
            raise MemoryRejected(
                "not_stored",
                "the memory engine did not store this text (it may duplicate an existing memory)",
            )
        now = datetime.now(tz=UTC)
        return MemoryRecord(
            id=memory_id,
            store_name=store_name,
            text=text,
            actor=actor,
            created_at=now,
            updated_at=now,
        )

    async def get(self, store_name: str, memory_id: str) -> MemoryRecord | None:
        client = self._require(store_name)
        try:
            payload = await asyncio.to_thread(client.get, memory_id)
        except Exception:
            return None
        if not payload:
            return None
        return _payload_to_record(store_name, payload)

    async def list(self, store_name: str, *, limit: int, offset: int) -> Sequence[MemoryRecord]:
        client = self._require(store_name)
        all_memories = await asyncio.to_thread(client.get_all, user_id=store_name)
        items = _extract_list(all_memories)
        chunk = items[offset : offset + limit]
        return [_payload_to_record(store_name, p) for p in chunk]

    async def update(
        self,
        store_name: str,
        memory_id: str,
        new_text: str,
        *,
        actor: Actor,
    ) -> MemoryRecord:
        client = self._require(store_name)
        async with self._lock(store_name):
            try:
                await asyncio.to_thread(client.update, memory_id, new_text)
            except Exception as exc:
                raise MemoryNotFound(store_name, memory_id) from exc
            # CODE26-022: mem0 may rewrite/condense the supplied text into
            # its canonical fact form; re-read so the persisted SQL row
            # mirrors what the vector index actually stores. ``client.get``
            # may transiently fail (e.g. mem0's storage commit lag); fall
            # back to the input text rather than abort the update.
            canonical_text = new_text
            try:
                payload = await asyncio.to_thread(client.get, memory_id)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                d = cast(dict[str, Any], payload)
                returned = d.get("memory") or d.get("text")
                if isinstance(returned, str) and returned:
                    canonical_text = returned
        now = datetime.now(tz=UTC)
        return MemoryRecord(
            id=memory_id,
            store_name=store_name,
            text=canonical_text,
            # CODE26-023: mem0 does not retain the post-update actor, so
            # the adapter stamps the caller-supplied actor here.
            actor=actor,
            created_at=now,
            updated_at=now,
        )

    async def delete(self, store_name: str, memory_id: str) -> bool:
        client = self._require(store_name)
        async with self._lock(store_name):
            try:
                await asyncio.to_thread(client.delete, memory_id)
                return True
            except Exception:
                return False

    async def clear(self, store_name: str) -> int:
        client = self._require(store_name)
        async with self._lock(store_name):
            try:
                await asyncio.to_thread(client.delete_all, user_id=store_name)
            except Exception:
                return 0
        return 0  # mem0 doesn't reliably return a count

    async def search(self, store_name: str, query: str, top_k: int) -> Sequence[MemoryHit]:
        client = self._require(store_name)
        result = await asyncio.to_thread(client.search, query, user_id=store_name, limit=top_k)
        items = _extract_list(result)
        hits: list[MemoryHit] = []
        for item in items[:top_k]:
            hits.append(
                MemoryHit(
                    id=str(item.get("id") or _short_uuid()),
                    text=str(item.get("memory") or item.get("text") or ""),
                    score=float(item.get("score", 0.0) or 0.0),
                    created_at=_parse_dt(item.get("created_at")) or datetime.now(tz=UTC),
                )
            )
        return hits

    async def drop(self, store_name: str) -> None:
        import contextlib

        async with self._lock(store_name):
            client = self._clients.pop(store_name, None)
            if client is not None:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(client.delete_all, user_id=store_name)
            self._configs.pop(store_name, None)

    async def close(self) -> None:
        self._clients.clear()
        self._configs.clear()
        self._locks.clear()

    def _require(self, store_name: str) -> Any:
        client = self._clients.get(store_name)
        if client is None:
            raise EngineUnavailable("mem0", f"store {store_name!r} was not opened")
        return client


def _build_memory_client(
    memory_cls: Any,
    config: MemoryStoreConfig,
    store_path: Path,
    llm_api_key: str | None = None,
) -> Any:
    """Construct a mem0 `Memory` configured for local persistent storage.

    Uses mem0's `from_config(...)` factory. ``llm_api_key`` is consumed only
    by the ``openai`` provider; ignored otherwise. Passing ``None`` for
    openai will leave mem0 to look up ``OPENAI_API_KEY`` from the process
    environment which, in Coffer's local-first model, is intentionally not
    populated — so the absence is surfaced by mem0 at first add().
    """
    # CODE26-013 / CODE26-034: mem0's huggingface embedder downloads a
    # sentence-transformers model on first use. As of mem0 0.x the
    # ``embedder.config`` block does not expose a ``trust_remote_code``
    # toggle — the upstream default is False for ``sentence-transformers``
    # which is what mem0 invokes here, so the risk is bounded but not
    # configurable from Coffer. Documented for follow-up if mem0 starts
    # accepting the flag, in which case we should set it explicitly to
    # ``False`` rather than rely on the upstream default.
    mem_config: dict[str, Any] = {
        "version": "v1.1",
        "embedder": {
            "provider": "huggingface",
            "config": {"model": config.embedding_model},
        },
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": "memories",
                "path": str(store_path / "chroma"),
            },
        },
    }
    if config.llm_provider == "ollama":
        mem_config["llm"] = {
            "provider": "ollama",
            "config": {
                "model": config.llm_model or "llama3.1",
                "ollama_base_url": config.effective_endpoint or "http://localhost:11434",
            },
        }
    elif config.llm_provider == "openai":
        openai_cfg: dict[str, Any] = {"model": config.llm_model or "gpt-4o-mini"}
        if llm_api_key:
            # CODE26-002: mem0's openai provider accepts ``api_key`` in its
            # config block; without it the SDK falls back to env which we
            # deliberately leave empty (local-first: secrets only via OS
            # keychain).
            openai_cfg["api_key"] = llm_api_key
        mem_config["llm"] = {
            "provider": "openai",
            "config": openai_cfg,
        }
    # llm_provider == "none": omit llm config; mem0's writes will fail, but reads work.
    if hasattr(memory_cls, "from_config"):
        return memory_cls.from_config(mem_config)
    return memory_cls(config=mem_config)


def _extract_id(payload: object) -> str | None:
    if isinstance(payload, dict):
        d = cast(dict[str, Any], payload)
        if "id" in d:
            return str(d["id"])
        if "results" in d and isinstance(d["results"], list) and d["results"]:
            first = d["results"][0]
            if isinstance(first, dict):
                v = cast(dict[str, Any], first).get("id")
                if v is not None:
                    return str(v)
    return None


def _extract_list(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [cast(dict[str, Any], p) for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        d = cast(dict[str, Any], payload)
        if "results" in d and isinstance(d["results"], list):
            return [p for p in d["results"] if isinstance(p, dict)]
        return [d]
    return []


def _payload_to_record(store_name: str, payload: dict[str, Any]) -> MemoryRecord:
    actor_meta = payload.get("metadata", {})
    actor: Actor = "agent"
    if isinstance(actor_meta, dict):
        candidate = actor_meta.get("actor")
        if candidate in ("agent", "user"):
            actor = candidate
    return MemoryRecord(
        id=str(payload.get("id") or _short_uuid()),
        store_name=store_name,
        text=str(payload.get("memory") or payload.get("text") or ""),
        actor=actor,
        created_at=_parse_dt(payload.get("created_at")) or datetime.now(tz=UTC),
        updated_at=_parse_dt(payload.get("updated_at")) or datetime.now(tz=UTC),
    )


def _parse_dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _short_uuid() -> str:
    return uuid.uuid4().hex
