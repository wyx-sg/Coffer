"""Follow-master-library reconciliation for SkillService (FR-025).

Extracted to keep ``service.py`` under the file-size limit. Free functions
that take the SkillService instance and reach into its (private) attributes —
conceptually private to the skill subpackage.

The per-agent policy (``follow_all_skills`` + ``skill_exclusions``) lives on
the agent resource's config (spec 004); SkillService reads it through the
injected ``agent_skill_policy_resolver`` so this module never imports
agent-kind code (Contract 5c).
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


async def apply_follow_for_agent(
    *, service: SkillService, agent_name: str, actor: str
) -> list[str]:
    """Reconcile an agent's deliveries with its follow policy (FR-025) and its
    ADR-045 activation scope (spec 005 amendment — delivery = scope ∩ follow
    policy, with reclaim).

    Invoked when the agent's policy changes (flag flip / exclusion edit),
    after registration (new agents default to follow-all), and by the sync
    post-import hook (spec 010 import reconciliation). While following, the
    effective set is the master store minus the exclusion list AND minus any
    skill whose scope excludes this agent: wanted-but-unbound
    skills are delivered, bound-but-excluded skills are removed. NOT
    following → no delivery (disabling the flag preserves the currently
    delivered set as explicit per-skill bindings) — but see below, reclaim
    still applies. Skills bound but missing from master are untouched here —
    master removal cascades via the skill kind's on_delete hook.

    Scope is a hard grant that overrides manual bindings: a previously
    delivered copy is ALWAYS reclaimed the instant its skill falls out of
    scope, regardless of the follow flag. The `agent` kind carries no scope
    of its own (ADR-045) — only the skill's scope gates delivery.

    Returns the per-skill delivery failures as human-readable strings so the
    sync hook can surface them in the run's errors; front-door callers ignore
    the return (the failures are logged).
    """
    try:
        agent = await service._rs.get(ResourceRef("agent", agent_name))
    except CofferError:
        return []
    follow, exclusions = service._resolve_agent_skill_policy(agent)
    skills = await service.list_skills()
    names_by_id = {s.id: s.name for s in skills}
    bound = {
        name
        for b in await service._bindings.list_for_agent(agent.id)
        if b.enabled and (name := names_by_id.get(b.skill_resource_id)) is not None
    }

    failures: list[str] = []
    excluded_reclaimed: set[str] = set()
    if follow:
        excluded = set(exclusions)
        wanted = {s.name for s in skills if agent_in_scope(s.scope, agent_name)} - excluded
        for name in sorted(wanted - bound):
            try:
                await service.enable_for(
                    skill_name=name, agent_name=agent_name, force=False, actor=actor
                )
            except (CofferError, OSError) as e:
                # Per-skill failures (TargetConflict, OSError, …) must not abort
                # the rest of the reconciliation — but they must be observable.
                logger.warning(
                    "follow delivery of skill %r to agent %r skipped: %s", name, agent_name, e
                )
                failures.append(f"skill {name!r}: {e}")
        excluded_reclaimed = bound & excluded
        for name in sorted(excluded_reclaimed):
            await service.disable_for(skill_name=name, agent_name=agent_name, actor=actor)

    # ALWAYS reclaim a bound skill the instant it falls out of scope — scope is
    # a hard grant overriding manual bindings, independent of the follow flag.
    out_of_scope = {s.name for s in skills if not agent_in_scope(s.scope, agent_name)}
    for name in sorted((bound & out_of_scope) - excluded_reclaimed):
        await service.disable_for(skill_name=name, agent_name=agent_name, actor=actor)

    return failures
