"""Wiring for the secret boundary: the gate, the presence grants, the destinations.

Spec secret "Hold a secret for a new destination until a person approves
it" and "Release plaintext only to a present human in the desktop app"; ADR
only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.

Owns the ``SecretBoundary`` and ``PresenceGrants`` singletons, the
``boundary_resolver`` every consumer of a secret is built with, the choice of
master-key storage by build identity, and the enumeration of every destination
in use — which feeds the one-time adoption at the first start and the refresh
that runs before approvals are listed.

A new destination type registers itself here with
:func:`register_resource_destination` (a resource kind) or calls
``get_secret_boundary().require(...)`` at its moment of use (anything else) —
the provider connection's base URL and a custom tool's auth are the next two.
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Awaitable, Callable, Mapping

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.secret.boundary import SecretBoundary
from coffer.application.secret.presence import PresenceGrants, derive_grant_key
from coffer.application.secret.resolver import SecretResolver, SecretStorePort
from coffer.domain.resource import Resource
from coffer.domain.secrets import SecretApproval, SecretDestination
from coffer.infrastructure.secret.boundary_store import FileBoundaryStore
from coffer.infrastructure.secret.build_identity import keychain_access_group
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.infrastructure.secret.keyring_adapter import KeyringAdapter
from coffer.infrastructure.secret.master_key import MasterKeyManager
from coffer.infrastructure.secret.master_key_backends import (
    ACCOUNT,
    KeychainAccessGroupBackend,
)
from coffer.infrastructure.vault.home import coffer_home
from coffer.surfaces.http.secret_schemas import ApprovalOut

#: One resource's secrets as the boundary sees them: where they go, and which
#: ref each slot cites. ``None`` when the resource sends nothing anywhere.
ResourceDestination = Callable[[Resource], tuple[SecretDestination, dict[str, str]] | None]
Current = list[tuple[SecretDestination, Mapping[str, str], str]]


_RESOURCE_DESTINATIONS: dict[str, ResourceDestination] = {}
#: Destinations that are not resources (the sync remote), each an async reader.
_OTHER_SOURCES: list[Callable[[], Awaitable[Current]]] = []


def register_resource_destination(kind: str, destination: ResourceDestination) -> None:
    """Declare where a kind's secrets go, so they are adopted and listed.

    Called by each kind's own wiring (the MCP and channel kinds today; the
    provider kind next), which is what keeps this module free of any kind.
    """
    _RESOURCE_DESTINATIONS[kind] = destination


def register_destination_source(source: Callable[[], Awaitable[Current]]) -> None:
    """Declare a destination that is not a resource — the sync remote's token."""
    _OTHER_SOURCES.append(source)


#: What to redo once an approval is applied: a destination built from state
#: (the model proxy's keys) is rebuilt so the newly approved secret reaches it.
_ON_APPROVED: list[Callable[[], None]] = []


def on_approval_applied(callback: Callable[[], None]) -> None:
    _ON_APPROVED.append(callback)


def approval_applied() -> None:
    for callback in list(_ON_APPROVED):
        callback()


_boundary: SecretBoundary | None = None
_grants: PresenceGrants | None = None


def get_secret_boundary() -> SecretBoundary:
    if _boundary is None:
        raise RuntimeError("secret boundary not initialised")
    return _boundary


def optional_secret_boundary() -> SecretBoundary | None:
    """The boundary once the daemon has built it; None in a bare test app."""
    return _boundary


def get_presence_grants() -> PresenceGrants:
    if _grants is None:
        raise RuntimeError("presence grants not initialised")
    return _grants


def set_secret_boundary(boundary: SecretBoundary | None, grants: PresenceGrants | None) -> None:
    """Called by the composition root once on startup (and by tests)."""
    global _boundary, _grants
    _boundary, _grants = boundary, grants


def boundary_resolver(store: SecretStorePort) -> SecretResolver:
    """The resolver every consumer of a secret gets: guarded once the daemon is up."""
    return SecretResolver(store, _boundary)


def master_key_path(home: pathlib.Path | None = None) -> pathlib.Path:
    """The development key file: ``~/.coffer/master.key``, wherever the
    history database is — the key opens the vault's ciphertext, so it follows
    the home the vault is in, not ``COFFER_DB_URL``."""
    return coffer_home(home) / "master.key"


def make_master_key_manager(home: pathlib.Path | None = None) -> MasterKeyManager:
    """The master key's home, chosen by how this build was made.

    A signed release carries its Team ID access group and keeps the key only
    there; anything else — a build from source — keeps the development
    arrangement (the ``0600`` file, the legacy keychain item when opted in).
    """
    group = keychain_access_group()
    vault = KeychainAccessGroupBackend(group) if group else None

    def backup(stamp: str) -> KeychainAccessGroupBackend:
        assert group is not None
        return KeychainAccessGroupBackend(group, account=f"{ACCOUNT}.bak-{stamp}")

    return MasterKeyManager(
        key_path=master_key_path(home),
        keyring=KeyringAdapter(),
        vault=vault,
        vault_backup=backup if group else None,
    )


def init_secret_boundary(
    store: EncryptedSecretStore,
    manager: MasterKeyManager,
    *,
    home: pathlib.Path | None = None,
) -> None:
    def grant_key() -> bytes | None:
        key = manager.current
        return derive_grant_key(key) if key else None

    set_secret_boundary(SecretBoundary(FileBoundaryStore(home), store), PresenceGrants(grant_key))


def approval_out(approval: SecretApproval) -> ApprovalOut:
    return ApprovalOut(
        id=approval.id,
        op=approval.op,
        status=approval.status,
        description=approval.describe(),
        created_at=approval.created_at,
        requested_by=approval.requested_by,
        ref=approval.ref,
        destination_kind=approval.destination_kind,
        destination_uid=approval.destination_uid,
        destination_label=approval.destination_label,
        slot=approval.slot,
        target=approval.target,
        decided_at=approval.decided_at,
        decided_by=approval.decided_by,
    )


async def _last_actor(audit: AuditService, resource: Resource) -> str:
    entries = await audit.query(resource=resource, limit=1)
    return entries[0].actor if entries else "unknown"


async def current_destinations(resources: ResourceService, audit: AuditService) -> Current:
    """Every place a secret is sent right now, with who last changed it."""
    out: Current = []
    for kind, describe in list(_RESOURCE_DESTINATIONS.items()):
        try:
            rows = await resources.list(kind=kind)
        except Exception:
            continue
        for resource in rows:
            try:
                found = describe(resource)
            except Exception:
                continue
            if found is not None:
                out.append((found[0], found[1], await _last_actor(audit, resource)))
    for source in list(_OTHER_SOURCES):
        out.extend(await source())
    return out


_sources: tuple[ResourceService, AuditService] | None = None


async def adopt_existing_bindings(resources: ResourceService, audit: AuditService) -> int:
    """Approve, once, every binding that was in use before the boundary existed.

    Also remembers where destinations are read from, for :func:`refresh_approvals`.
    """
    global _sources
    _sources = (resources, audit)
    boundary = get_secret_boundary()
    current = await current_destinations(resources, audit)
    return await asyncio.to_thread(boundary.adopt, current)


async def refresh_approvals() -> list[SecretApproval]:
    """Bring the approval list up to the configuration as it stands.

    Returns the approvals this refresh created. Before the daemon has read its
    destinations once (a test app without the startup pass), it does nothing.
    """
    if _sources is None:
        return []
    boundary = get_secret_boundary()
    current = await current_destinations(*_sources)
    return await asyncio.to_thread(boundary.refresh, current)


__all__ = [
    "adopt_existing_bindings",
    "approval_applied",
    "approval_out",
    "boundary_resolver",
    "current_destinations",
    "get_presence_grants",
    "get_secret_boundary",
    "init_secret_boundary",
    "make_master_key_manager",
    "master_key_path",
    "on_approval_applied",
    "optional_secret_boundary",
    "refresh_approvals",
    "register_destination_source",
    "register_resource_destination",
    "set_secret_boundary",
]
