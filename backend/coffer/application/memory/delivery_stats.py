"""What memory delivers — the Memory page's delivered view (spec memory "Show
what each agent is given at session start").

For one partition, the exact text each agent is given at session start in that
partition's repository. Whether a hook is installed or trusted is the agent's
own page (spec agent-registry "Connect an agent to Coffer in one action").
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.application.memory.context import MemoryPort, compose_context
from coffer.application.memory.delivery import DeliveryService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.memory.delivery import DELIVERY_CEILING_BYTES, SESSION_START


@dataclass(frozen=True)
class DeliveredText:
    agent_uid: str
    agent_name: str
    agent_type: str
    event: str
    text: str


class DeliveryStatsService:
    def __init__(
        self,
        *,
        memory: MemoryPort,
        delivery: DeliveryService,
    ) -> None:
        self._memory = memory
        self._delivery = delivery

    async def delivered(self, *, repository_path: str) -> list[DeliveredText]:
        """The session-start text each agent gets in ``repository_path`` —
        composed exactly as the hook composes it."""
        composed = await compose_context(
            self._memory, cwd=repository_path, ceiling_bytes=DELIVERY_CEILING_BYTES
        )
        out: list[DeliveredText] = []
        for site in await self._delivery.sites():
            cfg = AgentConfig.model_validate(site.agent.config)
            out.append(
                DeliveredText(
                    agent_uid=site.agent.uid,
                    agent_name=site.agent.name,
                    agent_type=cfg.type.value,
                    event=SESSION_START,
                    text=composed.text,
                )
            )
        return out


__all__ = ["DeliveredText", "DeliveryStatsService"]
