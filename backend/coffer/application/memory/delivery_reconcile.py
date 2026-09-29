"""Coffer's memory delivery hook, as a reconcile target.

ADR one-level-triggered-reconciler-compares-parameters. The hook Coffer puts in
an agent's settings file (Claude Code's ``settings.json``, Codex's
``hooks.json``) is judged by its **whole command** against what an install
would write now (``adapter.command_for(uid)``), not by its marker alone. That
is the rule PR #413 taught: when ``coffer memory context`` dropped ``--agent``
for ``--agent-uid``, every hook on disk kept the dead option and still read as
installed, because detection matched the marker and never read the arguments.

**What is wanted.** With the ``memory`` feature on, a current hook in every
agent connected to Coffer — every agent carrying the gateway MCP entry (spec
agent-registry "Connect an agent to Coffer in one action") — and in every agent
that already carries one, since installing it was that user's explicit act.
Which agents are connected is the agent kind's answer, handed in as
:data:`ConnectedAgents`, because this kind may not import that one. With
``memory`` off, no hook anywhere (spec experimental-features "Withdraw what a
switched-off feature put in front of agents").

**Direction policy** (:meth:`DeliveryHookTarget.decide`):

- a hook whose command or event differs is rewritten (``stale_command``, spec
  memory "Repair stale delivery hooks") — which moves an older build's Codex
  hook off ``UserPromptSubmit`` onto ``SessionStart``;
- a current hook the agent will not run (Codex's ``trust`` is not
  ``trusted``) is only reported (``hook_untrusted``, ``hook_disabled``,
  ``hook_trust_unknown``): approving a hook is the user's act in the agent,
  and Coffer never writes the agent's trust record;
- a hook with ``memory`` off is withdrawn (``feature_off``);
- a connected agent missing its hook gets one when ``memory`` was just
  switched on or a person asked (``Trigger.SWITCH`` / ``Trigger.MANUAL``), and
  is only reported otherwise: a boot or a period does not install a hook the
  user did not just ask for (spec memory "Install delivery hooks explicitly and
  removably"); the agent's page reports the connection as partial;
- an agent whose settings file does not parse is blocked
  (``unreadable_config``): nothing is guessed and nothing is written.

Writes go through :class:`DeliveryService`'s own marker-scoped, atomic,
backed-up writer; the audit event is the reconciler's to record.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from coffer.application.memory.delivery import DeliveryService, DeliveryWrite, HookSite
from coffer.application.reconcile.ports import Applied, AuditEvent, Undo
from coffer.domain.audit import AuditEventType
from coffer.domain.hook_trust import HookTrust
from coffer.domain.memory.delivery import MalformedDeliveryConfig
from coffer.domain.reconcile import (
    Decision,
    Difference,
    Disposition,
    Item,
    Op,
    PlannedChange,
    Subject,
    Trigger,
)

_log = logging.getLogger(__name__)

TARGET = "delivery_hook"
MEMORY_FEATURE = "memory"

#: The uids of the agents connected to Coffer.
ConnectedAgents = Callable[[], Awaitable[list[str]]]

#: The triggers on which a connected agent missing its hook is given one.
_INSTALL_TRIGGERS = frozenset({Trigger.SWITCH, Trigger.MANUAL})


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
        if key == MEMORY_FEATURE:
            await reconcile(features.is_enabled(MEMORY_FEATURE))

    return _on_switch


def _subject(site: HookSite) -> Subject:
    return Subject("agent", site.agent.uid, site.agent.title or site.agent.name)


class DeliveryHookTarget:
    """Implements ``ReconcileTarget`` for the memory delivery hook."""

    name = TARGET
    kinds = frozenset({"agent"})

    def __init__(
        self,
        *,
        delivery: DeliveryService,
        features: FeatureStatePort,
        connected: ConnectedAgents,
    ) -> None:
        self._delivery = delivery
        self._features = features
        self._connected = connected
        #: Agents whose file did not parse on the last observe, by uid. Read by
        #: the ``decide`` that follows it in the same (serialised) pass.
        self._unreadable: dict[str, str] = {}

    def _memory_on(self) -> bool:
        return self._features.is_enabled(MEMORY_FEATURE)

    async def desired(self) -> Sequence[Item]:
        if not self._memory_on():
            return []
        connected = set(await self._connected())
        items: list[Item] = []
        for site in await self._delivery.sites():
            if site.agent.uid not in connected and not self._carries_hook(site):
                continue
            command = site.adapter.command_for(site.agent.uid)
            params: dict[str, str] = {"event": site.adapter.event, "command": command}
            if site.trust_path is not None:
                params["trust"] = HookTrust.TRUSTED.value
            items.append(
                Item(
                    key=site.agent.uid,
                    subject=_subject(site),
                    params=params,
                    file=str(site.path),
                    text=command,
                )
            )
        return items

    def _carries_hook(self, site: HookSite) -> bool:
        try:
            return self._delivery.installed_command(site) is not None
        except MalformedDeliveryConfig:
            return False

    async def observe(self) -> Sequence[Item]:
        unreadable: dict[str, str] = {}
        items: list[Item] = []
        for site in await self._delivery.sites():
            try:
                hook = self._delivery.installed_hook(site)
            except MalformedDeliveryConfig as exc:
                _log.warning("delivery_hook: %s; left alone", exc)
                unreadable[site.agent.uid] = str(exc)
                continue
            if hook is None:
                continue
            # The event it actually sits on: an older build put Codex's hook
            # on UserPromptSubmit, and that is a difference to repair.
            params: dict[str, str] = {"event": hook.event, "command": hook.command}
            if site.trust_path is not None:
                params["trust"] = self._delivery.trust(site).value
            items.append(
                Item(
                    key=site.agent.uid,
                    subject=_subject(site),
                    params=params,
                    file=str(site.path),
                    text=hook.command,
                )
            )
        self._unreadable = unreadable
        return items

    def decide(self, differences: Sequence[Difference], trigger: Trigger) -> Sequence[Decision]:
        memory_on = self._memory_on()
        return [self._decide_one(d, trigger, memory_on=memory_on) for d in differences]

    def _decide_one(self, d: Difference, trigger: Trigger, *, memory_on: bool) -> Decision:
        if d.key in self._unreadable:
            return Decision(
                Disposition.BLOCKED,
                "unreadable_config",
                f"The agent's settings file does not parse ({self._unreadable[d.key]}), "
                "so Coffer cannot tell what is installed and writes nothing.",
            )
        if d.op is Op.MODIFY and d.changed_params == ("trust",):
            return self._untrusted(d)
        if d.op is Op.MODIFY:
            names = " and ".join(p for p in d.changed_params if p != "trust")
            return Decision(
                Disposition.REPAIR,
                "stale_command",
                f"The installed hook's {names} is not what this build would install; "
                "it is rewritten in place.",
            )
        if d.op is Op.REMOVE:
            if not memory_on:
                return Decision(
                    Disposition.REPAIR,
                    "feature_off",
                    "Memory is switched off, so Coffer's hook is withdrawn from this agent.",
                )
            # Memory on: every carried hook is wanted, so only a hook that
            # appeared between this pass's two reads lands here.
            return Decision(
                Disposition.REPORT,
                "hook_unexpected",
                "Coffer's hook appeared while this pass was reading; the next pass judges it.",
            )
        if trigger in _INSTALL_TRIGGERS:
            return Decision(
                Disposition.REPAIR,
                "hook_missing",
                "The agent is connected and memory is on, but its hook is missing; "
                "it is installed.",
            )
        return Decision(
            Disposition.REPORT,
            "hook_missing",
            "The agent is connected and memory is on, but its hook is missing; "
            "reconnecting the agent installs it.",
        )

    @staticmethod
    def _untrusted(d: Difference) -> Decision:
        """The hook is current but the agent will not run it: only the user
        can approve a hook in the agent, so this is reported, never written."""
        trust = str(d.observed.params.get("trust")) if d.observed else ""
        if trust == HookTrust.DISABLED.value:
            return Decision(
                Disposition.REPORT,
                "hook_disabled",
                "Coffer's hook is switched off in the agent, so it does not run; "
                "switch it back on in the agent's hook review (/hooks in Codex).",
            )
        if trust == HookTrust.UNKNOWN.value:
            return Decision(
                Disposition.REPORT,
                "hook_trust_unknown",
                "The agent's trust record does not parse, so Coffer cannot tell "
                "whether it will run Coffer's hook.",
            )
        return Decision(
            Disposition.REPORT,
            "hook_untrusted",
            "Coffer's hook needs approval in the agent before it runs: open Codex, "
            "run /hooks and trust Coffer's hook. Coffer does not approve its own hook.",
        )

    async def apply(self, change: PlannedChange) -> Applied:
        d = change.difference
        if d.op is Op.REMOVE:
            write = await self._delivery.write_remove(d.key)
            if write is None:
                # Gone since the pass observed it: nothing written, nothing to audit.
                return Applied(None)
            event = AuditEventType.MEMORY_DELIVERY_REMOVED
        else:
            write = await self._delivery.write_install(d.key)
            event = AuditEventType.MEMORY_DELIVERY_INSTALLED
        details: dict[str, object] = {
            **write.details,
            "reason": change.decision.reason_code,
            "repaired": list(d.changed_params),
        }
        return Applied(
            AuditEvent(event.value, write.agent, details),
            undo=self._undo(write),
        )

    def _undo(self, write: DeliveryWrite) -> Undo:
        async def _restore() -> None:
            self._delivery.restore(write)

        return _restore


__all__ = [
    "MEMORY_FEATURE",
    "TARGET",
    "ConnectedAgents",
    "DeliveryHookTarget",
    "FeatureStatePort",
    "MemorySwitchSubscriber",
    "memory_switch_subscriber",
]
