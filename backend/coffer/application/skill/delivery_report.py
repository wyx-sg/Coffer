"""What the last delivery pass did for one skill, agent by agent, so a reach
change can say which agents were linked and which failed (spec skill-manager
"Report per agent whether a reach change was delivered")."""

from __future__ import annotations

from dataclasses import dataclass

from coffer.application.skill.link_reconcile import split_key
from coffer.domain.reconcile import Outcome, PassReport
from coffer.domain.resource import Resource
from coffer.domain.scope import is_active


@dataclass(frozen=True)
class AgentDelivery:
    agent_uid: str
    agent_name: str
    ok: bool
    #: Why the link was not made; ``None`` when it was.
    reason: str | None = None


def delivery_for(
    skill: Resource, agents: list[Resource], report: PassReport | None
) -> list[AgentDelivery]:
    """One row per enabled agent the skill's reach grants, plus any agent a
    failed or blocked write names. An agent the pass had nothing to do for is ok."""
    problems: dict[str, str] = {}
    for r in report.results if report else ():
        skill_uid, agent_uid = split_key(r.change.difference.key)
        if skill_uid != skill.uid or r.outcome is Outcome.APPLIED:
            continue
        observed = r.change.difference.observed
        state = observed.params.get("state") if observed is not None else None
        problems[agent_uid] = r.error or (str(state) if state else "not written")
    by_uid = {a.uid: a for a in agents}
    wanted = [a for a in agents if a.enabled and skill.enabled and is_active(skill.scope, a.uid)]
    uids = list(dict.fromkeys([a.uid for a in wanted] + list(problems)))
    return [
        AgentDelivery(
            agent_uid=u,
            agent_name=by_uid[u].name if u in by_uid else u,
            ok=u not in problems,
            reason=problems.get(u),
        )
        for u in uids
    ]


__all__ = ["AgentDelivery", "delivery_for"]
