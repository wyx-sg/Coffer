"""The ref mover, wired: the store, this machine's approvals, the audit trail.

Called once from the lifespan after every kind has registered its secret
destinations (spec secret "Name a resource's secret after the resource and its
slot").
"""

from __future__ import annotations

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.secret.ref_names import RefMover
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.surfaces.http.secret_boundary_wiring import optional_secret_boundary


class _MachineRecords:
    """Bindings in the boundary; creation time and last-used stamp in the store."""

    def __init__(self, store: EncryptedSecretStore) -> None:
        self._store = store

    def carry(self, old: str, new: str) -> None:
        self._store.carry_records(old, new)
        boundary = optional_secret_boundary()
        if boundary is not None:
            boundary.rebind(old, new)


def wire_ref_names(
    resources: ResourceService, store: EncryptedSecretStore, audit: AuditService
) -> RefMover:
    """Renaming a channel or provider moves its secrets; the caller runs
    :meth:`RefMover.normalise` once for the rest."""
    mover = RefMover(resources, store, _MachineRecords(store), audit)
    resources.set_after_rename(mover.follow_rename)
    return mover
