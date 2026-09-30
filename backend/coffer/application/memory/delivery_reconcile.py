"""Coffer's memory delivery hook, as a reconcile target.

ADR one-level-triggered-reconciler-compares-parameters. The hook Coffer puts in
an agent's settings file (Claude Code's ``settings.json``, Codex's
``hooks.json``) is judged by its **whole command** against what an install
would write now (``adapter.command_for(uid)``), not by its marker alone. That
is the rule PR #413 taught: when a CLI flag the hook passes changes, every hook
on disk keeps the dead option and still reads as installed, because detection
matches the marker and never reads the arguments.

**What is wanted.** A current hook in every agent connected to Coffer — every
agent carrying the gateway MCP entry (spec agent-registry "Connect an agent to
Coffer in one action") — and in every agent that already carries one, since
installing it was that user's explicit act. Which agents are connected is the
agent kind's answer, handed in as :data:`ConnectedAgents`, because this kind
may not import that one.

**Direction policy** (:meth:`DeliveryHookTarget.decide`):

- a hook whose command or events differ is rewritten (``stale_command``, spec
  memory "Repair stale delivery hooks");
- a current hook the agent will not run (Codex's ``trust`` is not
  ``trusted``) is only reported (``hook_untrusted``, ``hook_disabled``,
  ``hook_trust_unknown``): approving a hook is the user's act in the agent,
  and Coffer never writes the agent's trust record;
- a connected agent missing its hook gets one when a person asked
  (``Trigger.MANUAL``), and is only reported otherwise: a boot or a period
  does not install a hook the user did not just ask for (spec memory "Install
  delivery hooks explicitly and removably"); the agent's page reports the
  connection as partial;
- an agent whose settings file does not parse is blocked
  (``unreadable_config``): nothing is guessed and nothing is written.

Writes go through :class:`DeliveryService`'s own marker-scoped, atomic,
backed-up writer; the audit event is the reconciler's to record.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence

from coffer.application.memory.delivery import DeliveryService, DeliveryWrite, HookSite
from coffer.application.reconcile.ports import Applied, AuditEvent, Undo
from coffer.domain.agent.types import agent_display_name
from coffer.domain.audit import AuditEventType
from coffer.domain.hook_trust import HookTrust
from coffer.domain.memory.delivery import MalformedDeliveryConfig, commands_label, events_label
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

#: The uids of the agents connected to Coffer.
ConnectedAgents = Callable[[], Awaitable[list[str]]]

#: The triggers on which a connected agent missing its hook is given one.
_INSTALL_TRIGGERS = frozenset({Trigger.MANUAL})


def _subject(site: HookSite) -> Subject:
    return Subject("agent", site.agent.uid, agent_display_name(site.agent.config, site.agent.name))


class DeliveryHookTarget:
    """Implements ``ReconcileTarget`` for the memory delivery hook."""

    name = TARGET
    kinds = frozenset({"agent"})

    def __init__(
        self,
        *,
        delivery: DeliveryService,
        connected: ConnectedAgents,
    ) -> None:
        self._delivery = delivery
        self._connected = connected
        #: Agents whose file did not parse on the last observe, by uid. Read by
        #: the ``decide`` that follows it in the same (serialised) pass.
        self._unreadable: dict[str, str] = {}

    async def desired(self) -> Sequence[Item]:
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
                hooks = self._delivery.installed_hooks(site)
            except MalformedDeliveryConfig as exc:
                _log.warning("delivery_hook: %s; left alone", exc)
                unreadable[site.agent.uid] = str(exc)
                continue
            if not hooks:
                continue
            # The events its entries actually sit on: a missing or extra
            # event is a difference to repair.
            command = commands_label([h.command for h in hooks])
            params: dict[str, str] = {
                "event": events_label([h.event for h in hooks]),
                "command": command,
            }
            if site.trust_path is not None:
                params["trust"] = self._delivery.trust(site).value
            items.append(
                Item(
                    key=site.agent.uid,
                    subject=_subject(site),
                    params=params,
                    file=str(site.path),
                    text=command,
                )
            )
        self._unreadable = unreadable
        return items

    def decide(self, differences: Sequence[Difference], trigger: Trigger) -> Sequence[Decision]:
        return [self._decide_one(d, trigger) for d in differences]

    def _decide_one(self, d: Difference, trigger: Trigger) -> Decision:
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
                # Read as-is on the Overview's Needs-you row when the rewrite
                # does not take, so it says what is wrong, not what a pass does.
                "Coffer's memory hook in this agent's settings no longer matches what "
                f"Coffer installs (its {names} changed).",
            )
        if d.op is Op.REMOVE:
            # Every carried hook is wanted, so only a hook that appeared
            # between this pass's two reads lands here.
            return Decision(
                Disposition.REPORT,
                "hook_unexpected",
                "Coffer's hook appeared while this pass was reading; the next pass judges it.",
            )
        if trigger in _INSTALL_TRIGGERS:
            return Decision(
                Disposition.REPAIR,
                "hook_missing",
                "The agent is connected, but its hook is missing; it is installed.",
            )
        return Decision(
            Disposition.REPORT,
            "hook_missing",
            "The agent is connected, but its hook is missing; reconnecting the agent installs it.",
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
    "TARGET",
    "ConnectedAgents",
    "DeliveryHookTarget",
]
