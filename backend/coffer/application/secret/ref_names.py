"""Name each resource's own secret after the resource and its slot.

Spec secret "Name a resource's secret after the resource and its slot": a secret
a resource owns is ``<kind>/<name>/<slot>``. This module moves a secret to that
name — at daemon start for every owned secret not yet named so, and after a
channel or provider is renamed.

A move is *copy, repoint, delete*, in an order that leaves the old ref cited
until the new one is proven:

1. write the value under the new ref and read it back;
2. carry this machine's records (bindings, creation time, last-used) to the new
   ref, so the secret boundary stays approved where it was;
3. change the citing config through the resource service (validated, audited,
   reconciled);
4. delete the old ref and audit ``secret_renamed``.

A failure before step 3 completes deletes the new ref (which forgets its
records) and leaves the old ref cited. A value is never logged or audited.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import logging
from typing import Any, Protocol

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.model_proxy.state import PROXY_TOKEN_REF_PREFIX
from coffer.domain.resource import Resource
from coffer.domain.secrets import (
    NAMED_SECRET_KINDS,
    is_named_for,
    is_standalone_ref,
    resource_secret_ref,
    slot_of,
)

_logger = logging.getLogger(__name__)
_ACTOR = "coffer"


class RefStore(Protocol):
    def set(self, ref: str, value: str) -> None: ...
    def peek(self, ref: str) -> str | None: ...
    def exists(self, ref: str) -> bool: ...
    def delete(self, ref: str) -> None: ...


class RefRecords(Protocol):
    """This machine's records kept per ref: approvals of where it may go, when
    it was stored, when it was last used."""

    def carry(self, old: str, new: str) -> None: ...


@dataclasses.dataclass(frozen=True, slots=True)
class OwnedRef:
    """One secret a resource owns: it is the only citer, in one slot."""

    resource: Resource
    #: The kind's secret-ref key (an env var, a header, a config field).
    key: str
    #: The slot name the ref is named by.
    slot: str
    ref: str

    def canonical_for(self, name: str) -> bool:
        return is_named_for(self.ref, self.resource.kind, name, self.slot)


def _with_ref(resource: Resource, key: str, new: str) -> dict[str, Any]:
    config = copy.deepcopy(resource.config)
    if resource.kind == "mcp_server":
        config["transport"]["secret_refs"][key] = new
    else:
        config[key] = new
    return config


class RefMover:
    def __init__(
        self,
        resources: ResourceService,
        store: RefStore,
        records: RefRecords,
        audit: AuditService,
    ) -> None:
        self._resources = resources
        self._store = store
        self._records = records
        self._audit = audit

    # --- what is owned --------------------------------------------------------

    async def owned(self) -> list[OwnedRef]:
        """Every secret exactly one resource cites in exactly one slot, of a kind
        that names its secrets. Standalone ``secret/…`` and a proxy token are
        never owned."""
        out: list[OwnedRef] = []
        for ref, citers in (await self._resources.cited_secret_refs()).items():
            if len(citers) != 1 or is_standalone_ref(ref) or ref.startswith(PROXY_TOKEN_REF_PREFIX):
                continue
            resource = citers[0]
            if resource.kind not in NAMED_SECRET_KINDS:
                continue
            keys = [k for k, v in self._resources.secret_slots(resource).items() if v == ref]
            slot = slot_of(resource.kind, keys[0]) if len(keys) == 1 else None
            if slot is not None:
                out.append(OwnedRef(resource, keys[0], slot, ref))
        return out

    async def _free_ref(self, kind: str, name: str, slot: str) -> str:
        cited = set(await self._resources.cited_secret_refs())
        n = 1
        while True:
            ref = resource_secret_ref(kind, name if n == 1 else f"{name}-{n}", slot)
            # Taken only when something cites it: a stored ref nothing cites is a
            # leftover of a deleted resource, and the move re-encrypts over it.
            if ref not in cited:
                return ref
            n += 1

    # --- the move -------------------------------------------------------------

    async def move(self, owned: OwnedRef, name: str) -> str | None:
        """Move ``owned`` to the ref named for ``name``; its new ref, or None when
        there was no value to move."""
        resource = owned.resource
        old = owned.ref
        value = await asyncio.to_thread(self._store.peek, old)
        if value is None:
            _logger.warning("secret.rename_skipped", extra={"ref": old, "reason": "no value here"})
            return None
        new = await self._free_ref(resource.kind, name, owned.slot)
        try:
            await asyncio.to_thread(self._store.set, new, value)
            if await asyncio.to_thread(self._store.peek, new) != value:
                raise RuntimeError("the store did not read the value back")
            await asyncio.to_thread(self._records.carry, old, new)
            # Re-read: the config may have moved on since the scan.
            current = await self._resources.get(resource.uid)
            await self._resources.update_config(
                resource.uid,
                _with_ref(current, owned.key, new),
                _ACTOR,
                allow_lifecycle_kind=True,
            )
        except BaseException:
            # The old ref is still cited; the new one never was (or the change
            # did not land). Deleting it forgets the records carried to it.
            await asyncio.to_thread(self._store.delete, new)
            raise
        try:
            await asyncio.to_thread(self._store.delete, old)
        except Exception:
            _logger.exception("secret.rename_old_left", extra={"ref": old})
        await self._audit.record(
            AuditEventType.SECRET_RENAMED.value,
            actor=_ACTOR,
            details={"from": old, "to": new, "kind": resource.kind, "resource": resource.name},
        )
        _logger.info("secret.renamed", extra={"from": old, "to": new, "kind": resource.kind})
        return new

    # --- the two callers ------------------------------------------------------

    async def normalise(self) -> int:
        """Move every owned secret not yet named for its resource; how many moved.
        Idempotent. One failure is logged and does not stop the rest."""
        moved = 0
        try:
            owned = await self.owned()
        except Exception:
            _logger.exception("secret.normalise_failed")
            return 0
        for item in owned:
            if item.canonical_for(item.resource.name):
                continue
            try:
                if await self.move(item, item.resource.name) is not None:
                    moved += 1
            except Exception as e:
                # The class name only: an error's text can quote a value.
                _logger.warning(
                    "secret.rename_failed",
                    extra={"ref": item.ref, "error": type(e).__name__},
                )
        return moved

    async def follow_rename(self, renamed: Resource, old_name: str) -> None:
        """After ``renamed`` took its new name, move the secrets it owns to it."""
        if renamed.kind not in NAMED_SECRET_KINDS:
            return
        for item in await self.owned():
            if item.resource.uid != renamed.uid or item.canonical_for(renamed.name):
                continue
            try:
                await self.move(item, renamed.name)
            except Exception as e:
                _logger.warning(
                    "secret.rename_failed",
                    extra={"ref": item.ref, "error": type(e).__name__},
                )
