"""One-time migration: legacy OS-keychain secrets -> encrypted store.

Runs at every daemon startup but only touches refs that are cited by a
registered resource AND absent from the encrypted store, so a completed
migration is a no-op (the OS keychain is never enumerated — refs come
from each kind's credential_ref_extractor). A locked/denied keychain
skips that ref; it will be retried on the next startup.
"""

from __future__ import annotations

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
) -> int:
    """Move every still-keychain-resident cited secret into the store."""
    moved = 0
    for resource in await repo.list():
        kind_def = kinds.get(resource.kind)
        extractor = getattr(kind_def, "credential_ref_extractor", None)
        if extractor is None:
            continue
        for ref in extractor(resource.config).values():
            if store.get(ref) is not None:
                continue
            try:
                value = legacy.get(ref)
            except CredentialLocked:
                continue
            if value is None:
                continue
            store.set(ref, value)
            legacy.delete(ref)
            await audit.record(
                AuditEventType.CREDENTIAL_MIGRATED.value,
                actor="system",
                details={"ref": ref},
            )
            moved += 1
    return moved
