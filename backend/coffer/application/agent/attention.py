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
- ``agent_not_connected`` — none are. Informational: an agent the person
  chose not to connect is not broken.
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence
from typing import Protocol

from coffer.application.agent.auto_detect import AgentDetection
from coffer.application.agent.connection_service import ConnectionState, ConnectionStatus
from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.detection import DetectionState
from coffer.domain.agent.types import AgentType, agent_display_name
from coffer.domain.resource import Resource

KIND = "agent"


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
    ) -> None:
        self._agents = agents
        self._detect = detect
        self._connection = connection

    async def items(self) -> Sequence[AttentionItem]:
        out: list[AttentionItem] = []
        for agent in await self._agents.list(kind=KIND):
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
        return None


__all__ = [
    "AgentAttentionSource",
    "AgentConnectionPort",
    "AgentDetectPort",
    "AgentListPort",
]
