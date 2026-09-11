"""Skill-delivery reconciliation for SkillService (FR-012a / FR-025).

Extracted to keep ``service.py`` under the file-size limit. Free functions
that take the SkillService instance and reach into its (private) attributes —
conceptually private to the skill subpackage.

One rule decides delivery, and nothing else does::

    delivered(skill, agent) == skill.enabled and agent_in_scope(skill.scope, agent)

Both halves live on the SKILL resource, so this module needs nothing from the
agent's config beyond its name (Contract 5c): the agent carries no
skill-delivery policy at all.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from coffer.domain.errors import CofferError
from coffer.domain.resource import ResourceRef
from coffer.domain.scope import agent_in_scope

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService

logger = logging.getLogger(__name__)


async def apply_scope_for_agent(*, service: SkillService, agent_name: str, actor: str) -> list[str]:
    """Reconcile one agent's delivered set against the delivery predicate.

    ``wanted`` is every skill that is enabled AND in scope for this agent.
    Skills in ``wanted`` but not yet held are delivered; skills held but no
    longer wanted are reclaimed (link removed, binding row marked spent).
    Skills bound but missing from master are untouched here — master removal
    cascades via the skill kind's on_delete hook.

    Invoked after an agent registers, after its config dir moves, when a
    skill's ``enabled`` flag or ``scope`` changes (the skill kind's two
    post-write hooks), on import, and by the sync post-import hook.

    Delivery is a hard grant in both directions: a copy is reclaimed the
    instant its skill is disabled or falls out of scope, and re-delivered the
    instant that reverses. The `agent` kind carries no scope of its own
    (ADR per-agent-resource-scope) — only the skill's own state gates delivery.

    Returns the per-skill delivery failures as human-readable strings so the
    sync hook can surface them in the run's errors; front-door callers ignore
    the return (the failures are logged). A failure on one skill never aborts
    the rest of the run.
    """
    try:
        agent = await service._rs.get(ResourceRef("agent", agent_name))
    except CofferError:
        return []
    skills = await service.list_skills()
    names_by_id = {s.id: s.name for s in skills}
    bound = {
        name
        for b in await service._bindings.list_for_agent(agent.id)
        if b.enabled and (name := names_by_id.get(b.skill_resource_id)) is not None
    }
    # A disabled agent wants nothing: the predicate decides which agents a skill
    # is FOR, but an agent the user switched off is one Coffer does not write
    # into at all. Everything already delivered is reclaimed below, and
    # re-enabling the agent runs this again and puts it back.
    wanted = (
        {s.name for s in skills if s.enabled and agent_in_scope(s.scope, agent_name)}
        if agent.enabled
        else set()
    )

    failures: list[str] = []
    for name in sorted(wanted - bound):
        try:
            await service.enable_for(
                skill_name=name, agent_name=agent_name, force=False, actor=actor
            )
        except (CofferError, OSError) as e:
            # Per-skill failures (TargetConflict, OSError, …) must not abort
            # the rest of the reconciliation — but they must be observable.
            logger.warning("delivery of skill %r to agent %r skipped: %s", name, agent_name, e)
            failures.append(f"skill {name!r}: {e}")
    for name in sorted(bound - wanted):
        await service.disable_for(skill_name=name, agent_name=agent_name, actor=actor)

    return failures
