"""Discover locally-installed agents (spec 004-agent-registry).

Scans each ``AgentType.detect_marker()`` and reports the agents that are
installed on disk but **not yet registered**, as *candidates*. Nothing is
registered automatically — the user confirms which candidates to add
(discovery + confirm). A previously-removed agent therefore re-appears on the
next scan, since a removal might have been accidental.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.application.agent.service import AgentService
from coffer.domain.agent.descriptor import is_agent_enabled
from coffer.domain.agent.types import AgentType


@dataclass(frozen=True)
class AgentCandidate:
    """An installed-but-unregistered agent the user may choose to add."""

    type: AgentType
    display_name: str
    config_dir: str
    default_skill_dir: str
    suggested_name: str


class AutoDetectService:
    """Read-only discovery of installed agents (no registration side effects)."""

    def __init__(self, *, agent_service: AgentService) -> None:
        self._agents = agent_service

    async def discover(self) -> list[AgentCandidate]:
        """Return installed agents that aren't registered yet, as candidates.

        Read-only: it never writes. The caller (UI/CLI) decides which
        candidates to register. Already-registered types are skipped so the
        list only ever shows actionable "add me" rows.
        """
        existing = {r.config.get("type") for r in await self._agents.list()}
        candidates: list[AgentCandidate] = []
        for t in AgentType:
            if not is_agent_enabled(t):
                continue
            if t.value in existing:
                continue
            if not t.detect_marker().exists():
                continue
            candidates.append(
                AgentCandidate(
                    type=t,
                    display_name=t.display_name,
                    config_dir=str(t.config_dir()),
                    default_skill_dir=str(t.default_skill_dir()),
                    suggested_name=t.default_name(),
                )
            )
        return candidates
