"""This machine's stable sync identity (spec 010 amendment, ADR-043).

Lazily mints the machine id (a ULID) on first access and keeps the
human-friendly display name editable. The identity is machine-local state
*about* the machine — it never syncs as vault data; the workspace ``machines/``
registry entry is derived from it at export time.
"""

from __future__ import annotations

from collections.abc import Callable

from coffer.application.audit_service import AuditService
from coffer.application.sync.ports import MachineIdentityPort
from coffer.domain.audit import AuditEventType
from coffer.domain.sync.models import MachineIdentity


class MachineIdentityService:
    def __init__(
        self,
        repo: MachineIdentityPort,
        audit: AuditService,
        *,
        new_id: Callable[[], str],
        default_name: Callable[[], str],
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._new_id = new_id
        self._default_name = default_name

    async def get(self) -> MachineIdentity:
        """This machine's identity, minted on first access."""
        existing = await self._repo.get()
        if existing is not None:
            return existing
        name = self._default_name().strip() or "coffer"
        return await self._repo.create(self._new_id(), name)

    async def rename(self, display_name: str, *, actor: str) -> MachineIdentity:
        """Change the display name; the machine id itself is immutable."""
        display_name = display_name.strip()
        if not display_name:
            raise ValueError("display_name must not be blank")
        await self.get()  # ensure the row exists before renaming
        renamed = await self._repo.set_display_name(display_name)
        await self._audit.record(
            AuditEventType.SYNC_MACHINE_RENAMED.value,
            actor=actor,
            details={"display_name": display_name},
        )
        return renamed
