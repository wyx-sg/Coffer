"""The one agent that answers for a type (spec agent-registry).

A conversation names an agent TYPE (``claude_code``, ``codex``), not an agent
resource. Everything that has to turn that type back into one registered agent
— the model catalogue's config-dir lookup and the environment a chat turn runs
under — asks this function, so the directory a picker reads its models from and
the directory the turn itself runs against can never be two different ones.
"""

from __future__ import annotations

from typing import Protocol

from coffer.domain.agent.config import AgentConfig
from coffer.domain.resource import Resource


class AgentLister(Protocol):
    """The agent registry, narrowed to the one call these lookups need
    (the same port ``ProviderService`` takes as ``agents``)."""

    async def list(self) -> list[Resource]: ...


async def answering_agent_config(agents: AgentLister, agent_key: str) -> AgentConfig | None:
    """The config of the first ENABLED agent resource of this type, or ``None``.

    One resource answers for the type, so what is read for a type is always one
    agent's answer rather than a blend of several. Disabled agents are skipped:
    the user has told Coffer to leave them alone. A row Coffer can no longer
    parse is skipped too — a read-only lookup must not fail on it; the agent
    routes surface it.
    """
    for resource in await agents.list():
        if not resource.enabled:
            continue
        try:
            cfg = AgentConfig.model_validate(resource.config)
        except ValueError:
            continue
        if cfg.type.value == agent_key:
            return cfg
    return None


__all__ = ["AgentLister", "answering_agent_config"]
