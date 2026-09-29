"""What memory delivered, and what the agents read — the Memory page's two
delivery views (spec memory "Count what memory delivered and what was read",
"Show what each agent is given at session start").

* **Overview.** Per agent with a delivery hook, over the last seven days: how
  many times memory reached it (every audited fire, by moment), when it last
  did, and how many distinct notes its sessions opened — read off the file
  paths its tool calls named, never their content, and ``None``
  ("unavailable") when its transcripts cannot be read.
* **Delivered.** For one partition, the exact text each agent is given at
  session start in that partition's repository.

Neither says whether a hook is installed or trusted: that is the agent's own
page (spec agent-registry "Connect an agent to Coffer in one action").
"""

from __future__ import annotations

import pathlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from coffer.application.audit_service import AuditService
from coffer.application.memory.context import MemoryPort, compose_context
from coffer.application.memory.delivery import DeliveryService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.delivery import DELIVERY_CEILING_BYTES, SESSION_START
from coffer.infrastructure.memory import paths as memory_paths
from coffer.infrastructure.memory import transcript_reads

#: The overview's window.
WINDOW_DAYS = 7
#: Enough rows for any real week of fires; the count says when it is capped.
_MAX_FIRES = 100_000

NotesRead = Callable[[str, pathlib.Path, pathlib.Path, datetime], set[str] | None]


@dataclass(frozen=True)
class AgentDeliveryStats:
    agent_uid: str
    agent_name: str
    agent_type: str
    deliveries: int
    by_moment: dict[str, int] = field(default_factory=dict)
    last_delivered_at: datetime | None = None
    #: Distinct notes the agent's sessions opened in the window; ``None`` when
    #: that could not be computed.
    notes_read: int | None = None


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
        audit: AuditService,
        notes_read: NotesRead = transcript_reads.notes_read,
    ) -> None:
        self._memory = memory
        self._delivery = delivery
        self._audit = audit
        self._notes_read = notes_read

    async def overview(
        self, *, days: int = WINDOW_DAYS, now: datetime | None = None
    ) -> list[AgentDeliveryStats]:
        since = (now or datetime.now(tz=UTC)) - timedelta(days=days)
        root = memory_paths.memory_root()
        out: list[AgentDeliveryStats] = []
        for site in await self._delivery.sites():
            agent = site.agent
            cfg = AgentConfig.model_validate(agent.config)
            fires = await self._audit.query(
                resource=agent,
                event_type=AuditEventType.MEMORY_DELIVERY_FIRED.value,
                since=since,
                limit=_MAX_FIRES,
            )
            moments = Counter(
                str((f.details or {}).get("moment") or "session_start") for f in fires
            )
            try:
                read = self._notes_read(
                    cfg.type.value, pathlib.Path(cfg.resolved_config_dir()), root, since
                )
            except Exception:
                read = None
            out.append(
                AgentDeliveryStats(
                    agent_uid=agent.uid,
                    agent_name=agent.name,
                    agent_type=cfg.type.value,
                    deliveries=len(fires),
                    by_moment=dict(sorted(moments.items())),
                    last_delivered_at=max((f.timestamp for f in fires), default=None),
                    notes_read=len(read) if read is not None else None,
                )
            )
        return out

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


__all__ = ["WINDOW_DAYS", "AgentDeliveryStats", "DeliveredText", "DeliveryStatsService"]
