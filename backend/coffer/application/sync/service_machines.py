"""The machines half of ``SyncService`` (spec vault-sync "Derive the registry
from the descriptors", "Treat the machine name as a label").

The registry is whatever ``machines/*.json`` holds at ``HEAD``: each machine
writes its own descriptor and no other's. Renaming this machine rewrites its
own descriptor now, as a person's commit, so the next round carries the new
label even when it has nothing else to push. Retiring another machine deletes
its descriptor in a person's commit; if that machine rounds again, its
descriptor comes back with it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from coffer.application.sync.views import MachineView
from coffer.domain.audit import AuditEventType
from coffer.domain.sync.errors import CannotRetireSelf, SyncMachineNameInvalid, SyncMachineNotFound
from coffer.domain.sync.machine import MachineDescriptor, descriptor_path, machine_id_of
from coffer.domain.vault.history import REMOVED, Commit
from coffer.domain.vault.layout import MACHINES
from coffer.domain.vault.writers import OP_DELETE, OP_UPDATE, WRITER_SYNC, WRITER_USER, CommitMeta
from coffer.domain.vault.writes import Expect

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.audit_service import AuditService
    from coffer.application.sync.round_engine import RoundEngine
    from coffer.application.sync.round_ports import RoundHistoryPort
    from coffer.application.sync.service_ports import HostMachinePort

MAX_NAME = 64
#: How far back the log is read for each machine's last merge.
_LOG_WINDOW = 300


class MachinesMixin:
    """Declares what it borrows from ``SyncService``, which assigns each."""

    _engine: RoundEngine
    _machine: HostMachinePort
    _history: RoundHistoryPort
    _audit: AuditService
    _set_machine_name: Callable[[str], None]

    async def _locked(self, fn: Callable[[], Any]) -> Any:
        raise NotImplementedError  # pragma: no cover - provided by SyncService

    #: ``(HEAD, descriptors)`` and ``(HEAD, last sync summary per machine)`` of the
    #: last read. A commit id names its tree and its history for good, so an
    #: answer read at one is never stale at that id; the next HEAD replaces it.
    _descriptors_memo: tuple[str, dict[str, MachineDescriptor]] | None = None
    _merges_memo: tuple[str, dict[str, str]] | None = None

    def _descriptors(self) -> dict[str, MachineDescriptor]:
        git = self._engine.d.git
        head = git.head()
        if head is None:
            return {}
        memo = self._descriptors_memo
        if memo is not None and memo[0] == head:
            return dict(memo[1])
        files = git.files(head, MACHINES)
        data = git.blobs(list(files.values()))
        out: dict[str, MachineDescriptor] = {}
        for path, blob in files.items():
            machine = machine_id_of(path)
            parsed = (
                MachineDescriptor.parse(machine, data[blob]) if machine and blob in data else None
            )
            if machine and parsed is not None:
                out[machine] = parsed
        self._descriptors_memo = (head, dict(out))
        return out

    def _last_merges(self, machines: set[str]) -> dict[str, str]:
        git = self._engine.d.git
        head = git.head()
        if head is None:
            return {}
        memo = self._merges_memo
        if memo is None or memo[0] != head:
            latest: dict[str, str] = {}
            for commit in git.log(start=head, limit=_LOG_WINDOW):
                who = commit.meta.machine
                if who is not None and who not in latest and commit.meta.writer == WRITER_SYNC:
                    latest[who] = commit.meta.summary
            memo = (head, latest)
            self._merges_memo = memo
        return {who: summary for who, summary in memo[1].items() if who in machines}

    async def machines(self) -> list[MachineView]:
        """Every machine in the registry, this one first; this machine is
        listed even before its first round has published it."""
        own = self._machine.machine_id()
        descriptors = await asyncio.to_thread(self._descriptors)
        if own not in descriptors:
            descriptors[own] = self._machine.describe(last_round_at=None, last_commit=None)
        others = {m for m in descriptors if m != own}
        merges = await asyncio.to_thread(self._last_merges, others)
        mine = self._machine.describe(last_round_at=None, last_commit=None).key_fingerprint
        last = await self._history.recent(1)
        views: list[MachineView] = []
        for machine, d in sorted(descriptors.items(), key=lambda kv: (kv[0] != own, kv[1].name)):
            views.append(
                MachineView(
                    descriptor=d,
                    is_self=machine == own,
                    key_matches=None
                    if mine is None or d.key_fingerprint is None
                    else mine == d.key_fingerprint,
                    last_round=(last[0].status.value if last else None)
                    if machine == own
                    else merges.get(machine),
                )
            )
        return views

    async def rename_self(self, name: str, *, actor: str) -> MachineView:
        label = name.strip()
        if not label or len(label) > MAX_NAME:
            raise SyncMachineNameInvalid(f"a machine name is 1 to {MAX_NAME} characters")
        await asyncio.to_thread(self._set_machine_name, label)

        def publish() -> MachineDescriptor:
            d = self._engine.d
            path = self._machine.descriptor_path()
            current = self._descriptors().get(self._machine.machine_id())
            data = self._machine.descriptor(
                last_round_at=current.last_round_at if current else None,
                last_commit=current.last_converged_commit if current else None,
            )
            meta = CommitMeta(
                writer=WRITER_USER,
                operation=OP_UPDATE,
                summary=f"Renamed this machine to {label}",
                actor=actor,
            )
            d.writer.write_file(
                path, data, meta=meta, expected=Expect.HEAD if current else Expect.ABSENT
            )
            return MachineDescriptor.parse(
                self._machine.machine_id(), data
            ) or self._machine.describe(last_round_at=None, last_commit=None)

        descriptor: MachineDescriptor = await self._locked(publish)
        return MachineView(descriptor=descriptor, is_self=True, key_matches=True)

    async def retire_machine(self, machine_id: str, *, actor: str) -> None:
        if machine_id == self._machine.machine_id():
            raise CannotRetireSelf(machine_id)

        def retire() -> MachineDescriptor:
            d = self._engine.d
            retired = self._descriptors().get(machine_id)
            if retired is None:
                raise SyncMachineNotFound(machine_id)
            meta = CommitMeta(
                writer=WRITER_USER,
                operation=OP_DELETE,
                summary=f"Retired machine {machine_id}",
                actor=actor,
            )
            d.writer.delete_file(descriptor_path(machine_id), meta=meta, expected=Expect.HEAD)
            return retired

        retired: MachineDescriptor = await self._locked(retire)
        await self._audit.record(
            AuditEventType.SYNC_MACHINE_REMOVED.value,
            actor=actor,
            details={
                "machine_id": machine_id,
                "name": retired.name,
                "hostname": retired.hostname,
                "os": retired.os,
            },
        )

    async def restore_machine(self, machine_id: str, *, actor: str) -> MachineView:
        """Undo a retire: register the machine again, with the descriptor it
        had the moment before it was retired (read from the vault's history).
        A machine that is registered already is returned as it is."""
        if machine_id == self._machine.machine_id():
            raise CannotRetireSelf(machine_id)

        def restore() -> None:
            d = self._engine.d
            if machine_id in self._descriptors():
                return
            path = descriptor_path(machine_id)
            # Newest first: the commit that removed the file, then the last
            # one that wrote it.
            written = [c for c in d.git.log(path, start="HEAD") if _wrote(c, path)]
            data = d.git.read(written[0].version, path) if written else None
            if data is None:
                raise SyncMachineNotFound(machine_id)
            meta = CommitMeta(
                writer=WRITER_USER,
                operation=OP_UPDATE,
                summary=f"Registered machine {machine_id} again",
                actor=actor,
            )
            d.writer.write_file(path, data, meta=meta, expected=Expect.ABSENT)

        await self._locked(restore)
        return next(v for v in await self.machines() if v.descriptor.machine_id == machine_id)


def _wrote(commit: Commit, path: str) -> bool:
    """Whether ``commit`` left ``path`` in the tree (it added or changed it)."""
    return any(p.path == path and p.status != REMOVED for p in commit.paths)


__all__ = ["MAX_NAME", "MachinesMixin"]
