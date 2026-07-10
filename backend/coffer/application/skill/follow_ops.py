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

import contextlib
import logging
from typing import TYPE_CHECKING

from coffer.application.skill.delivery_ops import delivers_skill_folders
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import CofferError
from coffer.domain.resource import ResourceRef
from coffer.domain.scope import agent_in_scope, machine_in_scope

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService

logger = logging.getLogger(__name__)


async def audit_autobind_skipped(
    *, service: SkillService, skill_name: str, agent_name: str, reason: str, actor: str
) -> None:
    """Best-effort SKILL_AUTOBIND_SKIPPED audit row (never raises)."""
    with contextlib.suppress(Exception):
        await service._audit.record(
            AuditEventType.SKILL_AUTOBIND_SKIPPED.value,
            ref=ResourceRef("skill", skill_name),
            actor=actor,
            details={"agent": agent_name, "reason": reason},
        )


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
    skill whose scope excludes this (machine, agent) pair: wanted-but-unbound
    skills are delivered, bound-but-excluded skills are removed. NOT
    following → no delivery (disabling the flag preserves the currently
    delivered set as explicit per-skill bindings) — but see below, reclaim
    still applies. Skills bound but missing from master are untouched here —
    master removal cascades via the skill kind's on_delete hook.

    Scope is a hard grant that overrides manual bindings: a previously
    delivered copy is ALWAYS reclaimed the instant its skill falls out of
    scope, regardless of the follow flag. If the AGENT's own resource scope
    excludes this machine, the whole run is a no-op — its config dir may not
    even exist here. No machine-id provider wired → no scope filtering at all
    (legacy contract, same as ChannelRuntime / the MCP gateway).

    Returns the per-skill delivery failures as human-readable strings so the
    sync hook can surface them in the run's errors; front-door callers ignore
    the return (the failures are audited there).
    """
    try:
        agent = await service._rs.get(ResourceRef("agent", agent_name))
    except CofferError:
        return []
    # Non-folder agents (rules_mdc — recognized extension point) can't receive
    # folder deliveries; skip reconciliation so registration / policy-change
    # flows don't crash. FOLDER and EXTERNAL_DIR agents follow the master library.
    if not delivers_skill_folders(service, agent):
        return []

    local = await service._local_machine_id()
    if local is not None and not machine_in_scope(agent.scope, local):
        # The agent itself isn't in scope on this machine — its config dir
        # may not even exist here. Touch nothing: no delivery, no reclaim.
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
        if local is not None:
            wanted = {
                s.name
                for s in skills
                if machine_in_scope(s.scope, local) and agent_in_scope(s.scope, local, agent_name)
            } - excluded
        else:
            wanted = {s.name for s in skills} - excluded
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
                # The sync hook re-runs this on EVERY import; a standing failure
                # would grow the audit log unboundedly. Sync failures surface in
                # the run's errors instead; front-door attempts stay audited.
                if actor != "sync":
                    await audit_autobind_skipped(
                        service=service,
                        skill_name=name,
                        agent_name=agent_name,
                        reason=str(e),
                        actor=actor,
                    )
        excluded_reclaimed = bound & excluded
        for name in sorted(excluded_reclaimed):
            await service.disable_for(skill_name=name, agent_name=agent_name, actor=actor)

    # ALWAYS reclaim a bound skill the instant it falls out of scope — scope is
    # a hard grant overriding manual bindings, independent of the follow flag.
    if local is not None:
        out_of_scope = {
            s.name
            for s in skills
            if not (machine_in_scope(s.scope, local) and agent_in_scope(s.scope, local, agent_name))
        }
        for name in sorted((bound & out_of_scope) - excluded_reclaimed):
            await service.disable_for(skill_name=name, agent_name=agent_name, actor=actor)

    return failures
