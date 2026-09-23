"""The machines half of ``ConvergeService`` (spec vault-sync).

Split out for the file-size tier, along the seam that was already there: these
three read and write the registry in the working tree, while the rest of the
service is about rounds. Kept as a mixin rather than a second service because
they need the same lock, the same remote and the same audit trail, and a second
object holding all three would be the service under another name.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from coffer.application.sync.machines import MachineRegistry, MachineView
from coffer.domain.audit import AuditEventType
from coffer.domain.sync.errors import BackupRemoteInvalid

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.audit_service import AuditService
    from coffer.application.sync.ports import BundlePort, SyncRemoteRepoPort


class MachinesMixin:
    """Declares what it borrows from the service it is mixed into.

    The annotations below are the contract, not state: ``ConvergeService``
    assigns every one of them in its constructor. Spelling them here is what
    lets this half be type-checked on its own instead of trusting that the
    other half happens to provide them.
    """

    _remotes: SyncRemoteRepoPort
    _audit: AuditService
    _lock: asyncio.Lock
    _bundle_factory: Callable[[Path], BundlePort]
    _set_machine_name: Callable[[str], None]

    async def machines(self, registry: MachineRegistry) -> list[MachineView]:
        bundle = await self._bundle()
        return await registry.list(bundle) if bundle is not None else []

    async def rename_self(self, registry: MachineRegistry, name: str) -> MachineView:
        """Rename this machine.

        Costs nothing else: nothing references a machine by its label — a
        channel's binding and the curation owner name the id — so no resource
        has to be rewritten. The name reaches the other machines on the next round,
        inside this machine's own descriptor.

        Two writes, and both are needed. ``_set_machine_name`` persists it, so
        it survives a restart; ``registry.rename`` is what makes the running
        daemon use it — the registry read the name once at wiring, so without
        this the descriptor it publishes every round would keep carrying the
        old label until the daemon was restarted, and this very call would
        answer with the name it just replaced.
        """
        name = name.strip()
        if not name:
            raise BackupRemoteInvalid("a machine name cannot be empty")
        await asyncio.to_thread(self._set_machine_name, name)
        registry.rename(name)
        return MachineView(
            descriptor=(await registry.describe_self()), is_self=True, key_matches=True
        )

    async def retire_machine(self, registry: MachineRegistry, machine_id: str) -> None:
        """Drop a machine from the registry.

        One change and one effect: the descriptor goes. Retiring used to strip
        the id out of every scope that named it as well, which is why it once
        returned a count; reach is machine-local now and no scope can name a
        machine, so there is nothing else in the vault to reach for and the
        audit entry records the machine alone.
        """
        bundle = await self._bundle()
        if bundle is None:
            # The registry lives in the working tree, so there is nothing to
            # retire from until a remote exists.
            raise BackupRemoteInvalid("no sync remote is configured on this machine")
        async with self._lock:
            await registry.retire(bundle, machine_id)
        await self._audit.record(
            AuditEventType.SYNC_MACHINE_REMOVED.value,
            actor="user",
            details={"machine_id": machine_id},
        )

    async def _bundle(self) -> BundlePort | None:
        remote = await self._remotes.get()
        if remote is None:
            return None
        return self._bundle_factory(Path(remote.worktree_path).expanduser())
