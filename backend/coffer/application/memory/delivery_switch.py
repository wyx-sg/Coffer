"""The memory delivery hook follows the ``memory`` feature switch.

Spec experimental-features "Withdraw what a switched-off feature put in front of
agents": switching ``memory`` off removes the delivery hook from every agent it
was installed in, and switching it on installs it again.

Installing is explicit (spec memory "Install delivery hooks explicitly and
removably"): nothing puts the hook into an agent the person never chose. So
"install it again" means into exactly the agents it was taken out of, and that
list has to outlive the daemon — a switch turned off, a restart, then on again
must still find its way back. The list is kept through
:class:`WithdrawnDeliveryPort`, on this machine only, like the switch itself.

The reconcile is the boot heal too: at boot a ``memory`` that is off makes sure
no hook is left in any agent, and one that is on puts back whatever an earlier
switch withdrew and then rewrites stale commands, as the heal always did.
"""

from __future__ import annotations

import logging
from typing import Protocol

from coffer.application.memory.delivery import DeliveryService
from coffer.domain.errors import ResourceNotFound

logger = logging.getLogger(__name__)

#: The actor on the install/remove audit events a switch causes.
FEATURE_ACTOR = "system:features"


class WithdrawnDeliveryPort(Protocol):
    """The agents a switched-off ``memory`` took the hook out of, by uid."""

    def read(self) -> list[str]: ...

    def write(self, uids: list[str]) -> None: ...


async def reconcile_delivery(
    delivery: DeliveryService,
    withdrawn: WithdrawnDeliveryPort,
    *,
    enabled: bool,
) -> tuple[str, ...]:
    """Bring every agent's hook in line with the switch. Returns notes to log.

    Best-effort per agent, like the heal it replaces: one unreadable settings
    file must not keep the others from being put right.
    """
    if not enabled:
        return await _withdraw(delivery, withdrawn)
    notes = list(await _restore(delivery, withdrawn))
    notes += await delivery.heal_drift()
    return tuple(notes)


async def _withdraw(delivery: DeliveryService, withdrawn: WithdrawnDeliveryPort) -> tuple[str, ...]:
    removed, notes = await delivery.remove_everywhere(actor=FEATURE_ACTOR)
    # Only the agents it actually left: one whose removal failed still has it,
    # and is not one to put back.
    withdrawn.write(sorted(set(withdrawn.read()) | set(removed)))
    return tuple(notes)


async def _restore(delivery: DeliveryService, withdrawn: WithdrawnDeliveryPort) -> tuple[str, ...]:
    pending = withdrawn.read()
    if not pending:
        return ()
    notes: list[str] = []
    left: list[str] = []
    for uid in pending:
        try:
            status = await delivery.install(uid, actor=FEATURE_ACTOR)
        except ResourceNotFound:
            # The agent was deleted while memory was off: nothing to put back.
            continue
        except Exception as exc:
            left.append(uid)
            notes.append(f"{uid}: could not reinstall the delivery hook ({exc!r})")
            continue
        notes.append(f"{status.agent_name}: delivery hook reinstalled, memory is switched on")
    withdrawn.write(left)
    return tuple(notes)


__all__ = ["FEATURE_ACTOR", "WithdrawnDeliveryPort", "reconcile_delivery"]
