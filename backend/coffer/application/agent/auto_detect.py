"""Auto-detect locally-installed agents on daemon startup.

Scans each `AgentType.detect_marker()`. For every type whose marker exists
**and** which is not already registered **and** is not on the suppression
list, registers a new agent with `auto_detected=True`.
"""

from __future__ import annotations

import asyncio
import logging

from coffer.application.agent.service import AgentService, SuppressionRepoPort
from coffer.application.audit_service import AuditService
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource, ResourceRef

_logger = logging.getLogger(__name__)


class AutoDetectService:
    def __init__(
        self,
        *,
        agent_service: AgentService,
        audit: AuditService,
        suppression_repo: SuppressionRepoPort,
    ) -> None:
        self._agents = agent_service
        self._audit = audit
        self._suppression = suppression_repo
        # Serialise concurrent `/agents/detect` calls so two clients can't
        # both observe "not registered yet" and race to register the same
        # type. The non-overlapping calls remain cheap.
        self._lock = asyncio.Lock()

    async def run_once(self, actor: str = "system") -> list[Resource]:
        """Scan + register newly-detected agents. Returns newly created ones."""
        async with self._lock:
            existing = {r.config.get("type") for r in await self._agents.list()}
            suppressed = set(await self._suppression.list_all())
            registered: list[Resource] = []
            for t in AgentType:
                if t.value in existing or t.value in suppressed:
                    continue
                if not t.detect_marker().exists():
                    continue
                try:
                    r = await self._agents.register(
                        agent_type=t,
                        name=_default_name_for(t),
                        skill_dir=None,
                        description=f"Auto-detected {t.display_name}.",
                        actor=actor,
                        auto_detected=True,
                    )
                except Exception:
                    # Auto-detect must not crash startup. Log + continue —
                    # silently swallowing makes "why didn't my agent show
                    # up?" debugging impossible.
                    _logger.exception(
                        "agent.auto_detect.register_failed",
                        extra={"agent_type": t.value},
                    )
                    continue
                await self._audit.record(
                    AuditEventType.AGENT_AUTO_REGISTERED.value,
                    ref=ResourceRef("agent", r.name),
                    actor=actor,
                    details={"agent_type": t.value},
                )
                registered.append(r)
            return registered


def _default_name_for(t: AgentType) -> str:
    """Stable, short name for auto-registered agents (overridable by user)."""
    return t.value.replace("_", "-")
