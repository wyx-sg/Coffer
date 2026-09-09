"""The machines directory: this machine's registry entry + fleet listing
(spec 010 / ADR-043). Split from ``service.py`` for the file-size tier."""

from __future__ import annotations

import asyncio
import platform as _platform
from datetime import UTC, datetime

from coffer.application.sync.identity import MachineIdentityService
from coffer.application.sync.ports import GitPort, WorkspacePort
from coffer.domain.sync.models import (
    MACHINE_ENTRY_HEARTBEAT_SECONDS,
    MachineEntry,
    MachineIdentity,
)


class MachineDirectory:
    def __init__(
        self,
        identity: MachineIdentityService,
        workspace: WorkspacePort,
        coffer_version: str | None,
    ) -> None:
        self._identity = identity
        self._workspace = workspace
        self._coffer_version = coffer_version

    def own_entry(
        self, identity: MachineIdentity, *, last_sync_at: datetime | None
    ) -> MachineEntry:
        return MachineEntry(
            machine_id=identity.machine_id,
            display_name=identity.display_name,
            platform=_platform.system().lower(),
            os_version=_platform.release(),
            coffer_version=self._coffer_version,
            last_sync_at=last_sync_at,
        )

    async def list(self) -> tuple[MachineIdentity, list[MachineEntry]]:
        """Every machine known to the vault, plus which one is this machine.

        The local machine always appears (synthesized before its first sync),
        and its entry always carries the live display name — the workspace
        copy may lag a rename until the next run."""
        identity = await self._identity.get()
        entries = await asyncio.to_thread(self._workspace.read_machine_entries)
        result: list[MachineEntry] = []
        seen_local = False
        for entry in entries:
            if entry.machine_id == identity.machine_id:
                seen_local = True
                result.append(self.own_entry(identity, last_sync_at=entry.last_sync_at))
            else:
                result.append(entry)
        if not seen_local:
            result.append(self.own_entry(identity, last_sync_at=None))
        return identity, result

    async def refresh_entry(self, identity: MachineIdentity, git: GitPort) -> None:
        """Rewrite this machine's registry entry only when the run has other
        changes, the name changed, or the entry is stale (the 24 h heartbeat)
        — an idle machine must not generate registry-only commit chains."""

        def _refresh() -> None:
            own = next(
                (
                    e
                    for e in self._workspace.read_machine_entries()
                    if e.machine_id == identity.machine_id
                ),
                None,
            )
            now = datetime.now(tz=UTC)
            stale = own is None or own.display_name != identity.display_name
            if not stale and own is not None:
                ts = own.last_sync_at
                if ts is not None and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                stale = ts is None or (now - ts).total_seconds() > MACHINE_ENTRY_HEARTBEAT_SECONDS
            if stale or git.has_changes():
                self._workspace.write_machine_entry(self.own_entry(identity, last_sync_at=now))

        await asyncio.to_thread(_refresh)
