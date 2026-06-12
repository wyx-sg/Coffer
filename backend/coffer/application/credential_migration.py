"""One-time migration: legacy OS-keychain secrets -> encrypted store.

Runs at every daemon startup but only touches refs that are cited by a
registered resource (or passed in ``extra_refs`` for non-resource owners
like chat models and the global embedding config) AND absent from the
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


class _CredentialStorePort(Protocol):
    """Local structural port (kind-agnostic — mirrors resource_service's)."""

    def get(self, ref: str) -> str | None: ...
    def set(self, ref: str, value: str) -> None: ...
    def delete(self, ref: str) -> None: ...


async def migrate_legacy_keychain(
    kinds: dict[str, Any],
    repo: Any,
    legacy: _CredentialStorePort,
    store: _CredentialStorePort,
    audit: Any,
    *,
    extra_refs: Iterable[str] = (),
) -> int:
    """Move every still-keychain-resident cited secret into the store.

    ``extra_refs`` carries credential refs cited by non-resource owners
    (chat models, the global embedding config) so they migrate alongside
    resource-cited refs instead of being stranded in the OS keychain.
    """
    moved = 0
    seen: set[str] = set()

    async def _move(ref: str) -> None:
        nonlocal moved
        if not ref or ref in seen:
            return
        seen.add(ref)
        if store.get(ref) is not None:
            return
        try:
            # to_thread: keychain reads can block on user prompts.
            value = await asyncio.to_thread(legacy.get, ref)
        except CredentialLocked:
            return
        if value is None:
            return
        # to_thread: the store write blocks on SQLite's busy_timeout; on the
        # event loop it would freeze the coroutine holding the write lock,
        # turning a wait into a guaranteed deadlock.
        await asyncio.to_thread(store.set, ref, value)
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


async def gather_extra_credential_refs(
    chat_model_repo: Any,
    embedding_config_svc: Any,
) -> list[str]:
    """Collect credential refs cited by non-resource owners.

    Chat models and the global embedding config cite secrets but are not
    registered resources, so their refs would otherwise be stranded in the
    OS keychain on upgrade. The embedding config row may not exist yet, in
    which case its ref is simply absent.
    """
    refs: list[str] = []
    for model_cfg in await chat_model_repo.list():
        if model_cfg.credential_ref:
            refs.append(model_cfg.credential_ref)
    embedding_ref = (await embedding_config_svc.get()).credential_ref
    if embedding_ref:
        refs.append(embedding_ref)
    return refs
