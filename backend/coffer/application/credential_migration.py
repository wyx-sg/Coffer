"""One-time migration: legacy OS-keychain secrets -> encrypted store.

Runs at every daemon startup but only touches refs that are cited by a
registered resource (or passed in ``extra_refs``, for a citer that is not a
resource) AND absent from the
encrypted store, so a completed migration is a no-op (the OS keychain is
never enumerated — refs come from each kind's credential_ref_extractor
plus ``extra_refs``). A locked/denied keychain skips that ref; it will be
retried on the next startup.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from contextlib import suppress
from typing import Any, Protocol

from coffer.domain.audit import AuditEventType
from coffer.domain.errors import CredentialLocked


class _LegacyStorePort(Protocol):
    """The OS keychain this migration drains. Sync, and slow: a read can block
    on a user prompt, so every call goes through ``asyncio.to_thread``."""

    def get(self, ref: str) -> str | None: ...
    def delete(self, ref: str) -> None: ...


class _StorePort(Protocol):
    """The destination store, addressed through its async facade.

    ``EncryptedCredentialStore`` mandates it: a sync read or write on the event
    loop stalls — or deadlocks against — the aiosqlite coroutine holding the
    write lock. This module used to hand-roll ``asyncio.to_thread`` around the
    sync methods for its writes while calling ``get`` straight on the loop,
    which is the drift the mandate exists to prevent."""

    async def aget(self, ref: str) -> str | None: ...
    async def aset(self, ref: str, value: str) -> None: ...


async def migrate_legacy_keychain(
    kinds: dict[str, Any],
    repo: Any,
    legacy: _LegacyStorePort,
    store: _StorePort,
    audit: Any,
    *,
    extra_refs: Iterable[str] = (),
) -> int:
    """Move every still-keychain-resident cited secret into the store.

    ``extra_refs`` carries credential refs cited by anything that is not a
    resource, so they migrate alongside resource-cited refs instead of being
    stranded in the OS keychain. Nothing passes any today — the global embedding
    config was the last such owner and now reads its key from the connection it
    names — but the seam is what keeps a future non-resource citer from being
    stranded.
    """
    moved = 0
    seen: set[str] = set()

    async def _move(ref: str) -> None:
        nonlocal moved
        if not ref or ref in seen:
            return
        seen.add(ref)
        if await store.aget(ref) is not None:
            return
        try:
            # to_thread: keychain reads can block on user prompts.
            value = await asyncio.to_thread(legacy.get, ref)
        except CredentialLocked:
            return
        if value is None:
            return
        await store.aset(ref, value)
        # The value is now safely in the store; a CredentialLocked here just
        # leaves a harmless keychain copy behind — suppress and continue
        # (it never needs retrying, the store already holds the ref).
        with suppress(CredentialLocked):
            await asyncio.to_thread(legacy.delete, ref)
        await audit.record(
            AuditEventType.CREDENTIAL_MIGRATED.value,
            actor="system",
            details={"ref": ref},
        )
        moved += 1

    for resource in await repo.list():
        kind_def = kinds.get(resource.kind)
        extractor = getattr(kind_def, "credential_ref_extractor", None)
        if extractor is None:
            continue
        for ref in extractor(resource.config).values():
            await _move(ref)
    for ref in extra_refs:
        await _move(ref)
    return moved
