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

from coffer.domain.audit import AuditEventType
from coffer.domain.errors import CofferError
from coffer.domain.resource import ResourceRef

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


async def apply_follow_for_agent(*, service: SkillService, agent_name: str, actor: str) -> None:
    """Reconcile an agent's deliveries with its follow policy (FR-025).

    Invoked when the agent's policy changes (flag flip / exclusion edit) and
    after registration (new agents default to follow-all). While following,
    the effective set is the entire master store minus the exclusion list:
    wanted-but-unbound skills are delivered, bound-but-excluded skills are
    removed. NOT following → return untouched (disabling the flag preserves
    the currently delivered set as explicit per-skill bindings). Skills bound
    but missing from master are untouched here — master removal cascades via
    the skill kind's on_delete hook.
    """
    try:
        agent = await service._rs.get(ResourceRef("agent", agent_name))
    except CofferError:
        return
    # Non-folder agents (Cursor/Hermes) can't receive folder-symlink deliveries;
    # skip reconciliation so registration / policy-change flows don't crash.
    if not service._is_folder_delivery(agent):
        return
    follow, exclusions = service._resolve_agent_skill_policy(agent)
    if not follow:
        return
    excluded = set(exclusions)
    skills = await service.list_skills()
    names_by_id = {s.id: s.name for s in skills}
    wanted = {s.name for s in skills} - excluded
    bound = {
        name
        for b in await service._bindings.list_for_agent(agent.id)
        if b.enabled and (name := names_by_id.get(b.skill_resource_id)) is not None
    }
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
            await audit_autobind_skipped(
                service=service, skill_name=name, agent_name=agent_name, reason=str(e), actor=actor
            )
    for name in sorted(bound & excluded):
        await service.disable_for(skill_name=name, agent_name=agent_name, actor=actor)
