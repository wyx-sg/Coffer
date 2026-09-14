"""The machine registry, which is a view rather than a table (spec vault-sync).

Each machine writes exactly one document — ``machines/<machine_id>.yaml`` — and
writes no other machine's. Because ownership is disjoint, two machines can
never stage a change to the same path, so these documents cannot conflict and
the registry needs no convergence machinery of its own. "The registry" is
simply whatever ``machines/*.yaml`` currently holds.

That is the whole difference from the 0.3.0 design, which kept a ``machines``
table keyed by ULIDs — a table that then had to be converged like any other
state, and whose keys meant nothing to the person reading them.
"""

from __future__ import annotations

import dataclasses
import platform
import socket
from datetime import date

from coffer.application.resource_service import ResourceService
from coffer.application.sync.ports import BundlePort
from coffer.domain.audit import AuditEventType
from coffer.domain.error_base import CofferError
from coffer.domain.sync.machine import MachineDescriptor


@dataclasses.dataclass(frozen=True, slots=True)
class MachineView:
    """One row of the machines table."""

    descriptor: MachineDescriptor
    is_self: bool
    #: Whether this machine's credentials can be decrypted here. None when
    #: either side has published no fingerprint yet.
    key_matches: bool | None


class MachineRegistry:
    """Reads the registry, writes this machine's own row, retires others."""

    def __init__(
        self,
        *,
        machine_id: str,
        machine_name: str,
        derived: bool,
        coffer_version: str,
        resources: ResourceService,
        key_fingerprint: str | None,
    ) -> None:
        self._machine_id = machine_id
        self._machine_name = machine_name
        self._derived = derived
        self._version = coffer_version
        self._resources = resources
        self._fingerprint = key_fingerprint

    @property
    def machine_id(self) -> str:
        return self._machine_id

    def rename(self, name: str) -> None:
        """Take the new display name for this machine.

        The registry holds the name because it is what publishes it: every
        descriptor it writes from here on carries the new label, so the other
        machines learn it on the next round. Without this the name is frozen at
        the composition root — the daemon would keep publishing the old one
        until it was restarted, and the surface that just renamed the machine
        would report the name it replaced.
        """
        self._machine_name = name

    @property
    def identity_is_derived(self) -> bool:
        """False when the id came from the local fallback file.

        Worth surfacing: such a machine does not survive deleting
        ``~/.coffer``. It reappears under a new id, and its old descriptor has
        to be retired by hand.
        """
        return self._derived

    async def describe_self(self) -> MachineDescriptor:
        agents = [r.name for r in await self._resources.list(kind="agent")]
        return MachineDescriptor(
            machine_id=self._machine_id,
            name=self._machine_name,
            os=f"{platform.system()} {platform.release()}".strip(),
            hostname=socket.gethostname(),
            coffer_version=self._version,
            key_fingerprint=self._fingerprint,
            agents=tuple(sorted(agents)),
        )

    async def publish_self(self, bundle: BundlePort, *, commit: str | None, today: date) -> None:
        """Write this machine's descriptor, restamping at most once a day.

        A machine that is running but idle must not commit a heartbeat every
        round — the history records changes, not ticks — so the convergence
        stamp only moves when the day does. "Last converged" therefore means
        the last *day* this machine converged, and the surfaces say so.

        The one exception is a descriptor that carries **no** commit yet. A
        machine's very first round has no pointer to publish — its base is the
        empty tree — so it writes a descriptor naming no commit, and the
        once-a-day rule would then freeze that absence in place until tomorrow.
        A returning machine recovers its base from exactly this field (spec
        vault-sync ``## Joining a remote``), so a machine reinstalled on the day
        it first converged would be refused as unrecoverable. Filling a missing
        commit in is one extra write, once, and then the day rule holds again.
        """
        existing = bundle.read_machine_descriptors().get(self._machine_id)
        previous = (
            MachineDescriptor.from_doc(self._machine_id, existing) if existing is not None else None
        )
        descriptor = await self.describe_self()
        if (
            previous is not None
            and previous.last_converged_on == today
            and (previous.last_converged_commit is not None or commit is None)
        ):
            descriptor = dataclasses.replace(
                descriptor,
                last_converged_on=today,
                last_converged_commit=previous.last_converged_commit,
            )
        else:
            descriptor = descriptor.stamped_on(today, commit)
        bundle.write_machine_descriptor(self._machine_id, descriptor.to_doc())

    async def list(self, bundle: BundlePort) -> list[MachineView]:
        views: list[MachineView] = []
        for machine_id, doc in sorted(bundle.read_machine_descriptors().items()):
            descriptor = MachineDescriptor.from_doc(machine_id, doc)
            views.append(
                MachineView(
                    descriptor=descriptor,
                    is_self=machine_id == self._machine_id,
                    key_matches=_compare(self._fingerprint, descriptor.key_fingerprint),
                )
            )
        return views

    async def retire(self, bundle: BundlePort, machine_id: str) -> None:
        """Remove a machine's descriptor. That is the whole of retiring one.

        It used to be two halves — delete the descriptor, then strip the id out
        of every ``scope.machines`` — and the second half is gone with the
        machine axis itself. Nothing outside the registry names a machine now,
        so there is nothing left to leave dangling — and with no resource to
        rewrite there is no actor to attribute the rewrite to either, which is
        why this takes none. The awkward part of the old version went the same
        way: rebuilding the scope as
        ``machines=remaining or None`` meant retiring the *last* machine a
        resource named silently turned "only on that machine" into "on every
        machine" — a widening nobody asked for, performed by a deletion.

        It answers with nothing, for the same reason: the count it used to
        return was how many scopes it rewrote.
        """
        if machine_id == self._machine_id:
            raise CannotRetireSelfError(machine_id)
        bundle.delete_machine_descriptor(machine_id)

    @staticmethod
    def audit_event() -> str:
        return AuditEventType.SYNC_MACHINE_REMOVED.value


def _compare(mine: str | None, theirs: str | None) -> bool | None:
    if mine is None or theirs is None:
        return None
    return mine == theirs


class CannotRetireSelfError(CofferError):
    """Retiring the machine you are standing on. Maps to 422."""

    code = "SYNC_CANNOT_RETIRE_SELF"

    def __init__(self, machine_id: str) -> None:
        super().__init__(
            f"{machine_id} is this machine; retire it from another machine, or "
            "clear the sync remote here instead"
        )
