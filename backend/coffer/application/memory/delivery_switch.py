"""The memory delivery hook follows the ``memory`` feature switch.

Spec experimental-features "Withdraw what a switched-off feature put in front of
agents": switching ``memory`` off removes the delivery hook from every agent it
was installed in, and switching it on installs it into every agent connected to
Coffer.

Installing is explicit (spec memory "Install delivery hooks explicitly and
removably"): nothing puts the hook into an agent the person never chose. The
choice is connecting the agent (spec agent-registry "Connect an agent to Coffer
in one action"), which installs the hook while ``memory`` is on; so switching
``memory`` on puts the hook into exactly the agents that are connected — which
agents those are is the agent kind's answer, handed in as a callable by the
composition root, because this kind may not import that one.

At boot a ``memory`` that is off makes sure no hook is left in any agent, and
one that is on rewrites stale commands, as the heal always did. Boot does not
install into connected agents that lack the hook: a hook missing from a
connected agent is a connection the agent's page reports as needing repair, and
repairing it is the user's act, not a side effect of a restart.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from coffer.application.memory.delivery import DeliveryService

#: The actor on the install/remove audit events a switch causes.
FEATURE_ACTOR = "system:features"

#: The uids of the agents connected to Coffer.
ConnectedAgents = Callable[[], Awaitable[list[str]]]


class FeatureStatePort(Protocol):
    """Reads a feature's state as it is now (``FeatureService`` is one)."""

    def is_enabled(self, key: str) -> bool: ...


#: Called with the feature key and the value the switch set it to.
MemorySwitchSubscriber = Callable[[str, bool], Awaitable[None]]


def memory_switch_subscriber(
    features: FeatureStatePort, reconcile: Callable[[bool], Awaitable[None]]
) -> MemorySwitchSubscriber:
    """A feature subscriber that reconciles the hook whenever ``memory`` switches.

    It reconciles to the state ``memory`` is in when it runs, not to the value
    the switch passed: a subscriber that runs late — after a second switch has
    already landed — then converges on what is true now instead of undoing it.
    """

    async def _on_switch(key: str, _enabled: bool) -> None:
        if key == "memory":
            await reconcile(features.is_enabled("memory"))

    return _on_switch


async def reconcile_at_boot(delivery: DeliveryService, *, enabled: bool) -> tuple[str, ...]:
    """Boot: withdraw everywhere when ``memory`` is off, heal stale commands
    when it is on. Returns notes to log."""
    if not enabled:
        return await delivery.remove_everywhere(actor=FEATURE_ACTOR)
    return await delivery.heal_drift()


async def reconcile_on_switch(
    delivery: DeliveryService, connected: ConnectedAgents, *, enabled: bool
) -> tuple[str, ...]:
    """A switch: off withdraws everywhere; on installs into every connected
    agent that lacks the hook, then heals. Returns notes to log.

    Best-effort per agent: one unreadable settings file must not keep the
    others from being put right.
    """
    if not enabled:
        return await delivery.remove_everywhere(actor=FEATURE_ACTOR)
    notes = list(await _install_into(delivery, await connected()))
    notes += await delivery.heal_drift()
    return tuple(notes)


async def _install_into(delivery: DeliveryService, uids: list[str]) -> tuple[str, ...]:
    notes: list[str] = []
    for uid in uids:
        try:
            status = await delivery.status(uid)
            if status.installed:
                continue
            await delivery.install(uid, actor=FEATURE_ACTOR)
        except Exception as exc:
            notes.append(f"{uid}: could not install the delivery hook ({exc!r})")
            continue
        notes.append(f"{status.agent_name}: delivery hook installed, memory is switched on")
    return tuple(notes)


__all__ = [
    "FEATURE_ACTOR",
    "ConnectedAgents",
    "FeatureStatePort",
    "memory_switch_subscriber",
    "reconcile_at_boot",
    "reconcile_on_switch",
]
