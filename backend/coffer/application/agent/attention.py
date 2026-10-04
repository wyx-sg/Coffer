"""What about the registered agents needs a person (the Overview list).

At most one item per enabled agent, the most basic problem first:

- ``agent_program_missing`` — the agent's program is not on this machine
  (detection reads ``config_only`` or ``missing``). Nothing else about the
  agent matters until it is installed again, which is a chore for an agent:
  the item carries the prompt that hands reinstalling it over;
- ``agent_config_unreadable`` — reading its Coffer connection from the agent's
  own files raised (a config file that does not parse);
- ``agent_partial`` — some of the parts Coffer writes into it are in place
  and some are not;
- ``agent_hook_attention`` — connected, and the agent will run Coffer's memory
  hook (no review step, or it approved this definition), yet the hook has never
  fired. Only while the memory feature is on: with it off Coffer installs no
  hook, so its absence is not a problem. A hook the agent will not run —
  unapproved, approved for an earlier command, switched off, an unreadable
  trust record — is the reconciler's memory-hook target's to report
  (``hook_untrusted`` and its siblings), so it is not listed twice;
- ``agent_not_connected`` — none are. Informational: an agent the person
  chose not to connect is not broken.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable, Sequence
from typing import Protocol

from coffer.application.agent.auto_detect import AgentDetection
from coffer.application.agent.connection_service import ConnectionState, ConnectionStatus
from coffer.application.agent.hooks_service import CofferHook
from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.detection import DetectionState
from coffer.domain.agent.types import AgentType, agent_display_name
from coffer.domain.hook_trust import HookTrust
from coffer.domain.resource import Resource

KIND = "agent"

#: The trust values under which the agent runs Coffer's hook.
_RUNS = frozenset({HookTrust.NOT_REQUIRED, HookTrust.TRUSTED})


class AgentListPort(Protocol):
    """The kind-agnostic resource service, as far as this source reads it."""

    async def list(
        self, kind: str | None = None, enabled: bool | None = None
    ) -> Sequence[Resource]: ...


class AgentDetectPort(Protocol):
    async def detect(self, agent_type: AgentType, config_dir: pathlib.Path) -> AgentDetection: ...

    async def program_handoff(
        self, agent_type: AgentType, config_dir: str, state: DetectionState, *, registered: bool
    ) -> str | None: ...


class AgentConnectionPort(Protocol):
    async def status(self, agent_uid: str) -> ConnectionStatus: ...


class AgentHooksPort(Protocol):
    async def coffer_hook(self, uid: str) -> CofferHook | None: ...


def _check(uid: str) -> AttentionAction:
    return AttentionAction(verb="check", method="GET", path=f"/api/v1/agents/{uid}")


def _connect(uid: str) -> AttentionAction:
    return AttentionAction(
        verb="connect", method="POST", path=f"/api/v1/agents/{uid}/coffer-connection"
    )


class AgentAttentionSource:
    name = "agent"
    feature: str | None = None

    def __init__(
        self,
        *,
        agents: AgentListPort,
        detect: AgentDetectPort,
        connection: AgentConnectionPort,
        hooks: AgentHooksPort | None = None,
        memory_on: Callable[[], bool] | None = None,
    ) -> None:
        self._agents = agents
        self._detect = detect
        self._connection = connection
        self._hooks = hooks
        # None: not told, so the hook is judged (a daemon wired without the feature switch).
        self._memory_on = memory_on

    async def items(self) -> Sequence[AttentionItem]:
        out: list[AttentionItem] = []
        for agent in await self._agents.list(kind=KIND, enabled=True):
            item = await self._item(agent)
            if item is not None:
                out.append(item)
        return out

    async def _item(self, agent: Resource) -> AttentionItem | None:
        title = agent_display_name(agent.config, agent.name)
        cfg = AgentConfig.model_validate(agent.config)
        config_dir = cfg.resolved_config_dir()
        detection = await self._detect.detect(cfg.type, config_dir)
        if not detection.state.installed:
            return AttentionItem(
                kind=KIND,
                uid=agent.uid,
                title=title,
                reason_code="agent_program_missing",
                reason="Its program is not installed on this machine.",
                severity=Severity.ERROR,
                action=_check(agent.uid),
                handoff=await self._detect.program_handoff(
                    cfg.type, str(config_dir), detection.state, registered=True
                ),
            )
        try:
            status = await self._connection.status(agent.uid)
        except Exception as exc:
            return AttentionItem(
                kind=KIND,
                uid=agent.uid,
                title=title,
                reason_code="agent_config_unreadable",
                reason=f"Its configuration could not be read: {exc}",
                severity=Severity.WARNING,
                action=_check(agent.uid),
            )
        if status.state is ConnectionState.PARTIAL:
            missing = ", ".join(p.key for p in status.parts if not p.installed)
            return AttentionItem(
                kind=KIND,
                uid=agent.uid,
                title=title,
                reason_code="agent_partial",
                reason=f"Only part of its Coffer connection is in place (missing: {missing}).",
                severity=Severity.WARNING,
                action=_connect(agent.uid),
            )
        if status.state is ConnectionState.DISCONNECTED:
            return AttentionItem(
                kind=KIND,
                uid=agent.uid,
                title=title,
                reason_code="agent_not_connected",
                reason="It is not connected to Coffer.",
                severity=Severity.INFO,
                action=_connect(agent.uid),
            )
        return await self._hook_item(agent.uid, title)

    async def _hook_item(self, uid: str, title: str) -> AttentionItem | None:
        """A connected agent that runs Coffer's hook, but the hook never fired."""
        if self._hooks is None or (self._memory_on is not None and not self._memory_on()):
            return None
        hook = await self._hooks.coffer_hook(uid)
        if hook is None:
            return None
        # Any other trust is the reconciler's hook_untrusted family: reporting
        # it here too put the same problem on Overview twice.
        if hook.trust not in _RUNS or hook.last_fired_at is not None:
            return None
        return AttentionItem(
            kind=KIND,
            uid=uid,
            title=title,
            reason_code="agent_hook_attention",
            reason="Coffer's memory hook has never fired.",
            severity=Severity.WARNING,
            action=_check(uid),
        )


__all__ = [
    "AgentAttentionSource",
    "AgentConnectionPort",
    "AgentDetectPort",
    "AgentHooksPort",
    "AgentListPort",
]
