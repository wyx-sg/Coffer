"""Skill-delivery reconciliation for SkillService (FR-012 / FR-019).

Extracted to keep ``service.py`` under the file-size limit. Free functions
that take the SkillService instance and reach into its (private) attributes —
conceptually private to the skill subpackage.

One rule decides delivery, and nothing else does::

    delivered(skill, agent) == skill.enabled and scope.is_active(skill.scope, agent.uid)

Both halves live on the SKILL resource, so this module needs nothing from the
agent's config (Contract 5c): the agent carries no skill-delivery policy at
all. The uid on the right-hand side is the agent's identity, which is what the
scope stores — there is one vocabulary here and it is the one the user cannot
change out from under a reference.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from coffer.domain.errors import CofferError
from coffer.domain.scope import is_active

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService

logger = logging.getLogger(__name__)


async def apply_scope_for_agent(*, service: SkillService, agent_uid: str, actor: str) -> list[str]:
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
        agent = await service._rs.get(agent_uid)
    except CofferError:
        return []
    skills = await service.list_skills()
    # Two maps over the same rows: the binding table joins on the integer
    # ``resources.id``, while everything this function decides and reports is
    # keyed on the uid. Neither is a translation between two names for the same
    # thing — the id is the join key, the uid is the identity.
    by_id = {s.id: s for s in skills}
    by_uid = {s.uid: s for s in skills}
    bound = {
        skill.uid
        for b in await service._bindings.list_for_agent(agent.id)
        if b.enabled and (skill := by_id.get(b.skill_resource_id)) is not None
    }
    # A disabled agent wants nothing: the predicate decides which agents a skill
    # is FOR, but an agent the user switched off is one Coffer does not write
    # into at all. Everything already delivered is reclaimed below, and
    # re-enabling the agent runs this again and puts it back.
    wanted = (
        {s.uid for s in skills if s.enabled and is_active(s.scope, agent.uid)}
        if agent.enabled
        else set()
    )

    # Sorted by NAME, not by uid: a uid is random, so ordering by it would make
    # the sequence of deliveries — and of any failures reported below —
    # arbitrary from one run to the next.
    def _by_name(uid: str) -> str:
        return by_uid[uid].name

    failures: list[str] = []
    for uid in sorted(wanted - bound, key=_by_name):
        name = by_uid[uid].name
        try:
            await service.enable_for(skill_uid=uid, agent_uid=agent.uid, force=False, actor=actor)
        except (CofferError, OSError) as e:
            # Per-skill failures (TargetConflict, OSError, …) must not abort
            # the rest of the reconciliation — but they must be observable.
            logger.warning("delivery of skill %r to agent %r skipped: %s", name, agent.name, e)
            failures.append(f"skill {name!r}: {e}")
    for uid in sorted(bound - wanted, key=_by_name):
        await service.disable_for(skill_uid=uid, agent_uid=agent.uid, actor=actor)

    return failures
