"""Per-agent enable/disable binding operations for SkillService.

Extracted to keep ``service.py`` under the file-size limit. Like
``lifecycle_ops.py`` / ``scan_ops.py`` these are free functions that take
the SkillService instance and reach into its (private) attributes — they are
conceptually private to the skill subpackage.
"""

from __future__ import annotations

import contextlib
import pathlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from coffer.application.skill.delivery_ops import (
    delivers_skill_folders,
    reconcile_external_registration,
    resolve_agent_skill_delivery,
)
from coffer.application.skill.lifecycle_ops import infer_link_mode
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import TargetConflict
from coffer.domain.resource import ResourceRef
from coffer.domain.skill.binding import BindingState
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.content_scan import verdict_requires_ack
from coffer.domain.workspace_errors import SkillDeliveryUnsupported, SkillRiskNotAcknowledged

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService


async def enable_skill_for_agent(
    *,
    service: SkillService,
    skill_name: str,
    agent_name: str,
    force: bool,
    actor: str,
    skip_risk_gate: bool = False,
) -> BindingState:
    skill = await service._rs.get(ResourceRef("skill", skill_name))
    agent = await service._rs.get(ResourceRef("agent", agent_name))
    # Trust gate (FR-029): refuse to enable a skill whose content scan flagged
    # high/critical risk that hasn't been acknowledged. The follow / auto-bind
    # reconcilers catch this and record SKILL_AUTOBIND_SKIPPED, so a flagged
    # skill is simply not delivered until acknowledged. ``skip_risk_gate`` is
    # the adoption carve-out: adopting consolidates a skill the agent already
    # had, so it must not be blocked (and must not silently set the ack flag).
    if not skip_risk_gate:
        cfg = SkillConfig.model_validate(skill.config)
        if not cfg.risk_acknowledged and verdict_requires_ack(cfg.scan_verdict):
            raise SkillRiskNotAcknowledged(skill_name, cfg.scan_verdict or "high")
    # Gate delivery modes that have no on-disk folder delivery wired BEFORE any
    # filesystem work. FOLDER (own skills dir) and EXTERNAL_DIR (a Coffer-owned
    # dir the agent scans — Hermes) are both folder-style; Cursor's rules_mdc is
    # a recognized extension point the folder model must not mis-deliver into,
    # so it fails explicitly (422).
    mode = resolve_agent_skill_delivery(service, agent)
    if not delivers_skill_folders(service, agent):
        agent_type = str(agent.config.get("type", "")) if isinstance(agent.config, dict) else ""
        raise SkillDeliveryUnsupported(agent_type, mode)
    # For EXTERNAL_DIR agents the resolver returns the Coffer-owned external dir
    # (not the agent's own skills dir); the link mechanics below are identical.
    target_dir = service._resolve_agent_skill_dir(agent)
    link_path = target_dir / skill_name
    master = service._store.paths_for(skill_name).folder

    # The mode recorded on any prior binding — needed so a copy-fallback
    # target (a real directory by design) isn't misread as drift.
    prior = await service._bindings.find(skill_id=skill.id, agent_id=agent.id)
    prior_mode = prior.link_mode if prior else None

    # Resolve target conflicts.
    if link_path.exists() or link_path.is_symlink():
        status = service._sync.classify_target(
            link=link_path, expected_master=master, link_mode=prior_mode
        )
        if status.drift is None:
            # Already linked correctly — idempotent. Record the mode that
            # actually exists on disk (not a SYMLINK assumption) so a
            # junction/copy-fallback isn't mislabelled when no prior row
            # existed.
            binding = await service._bindings.upsert(
                skill_id=skill.id,
                agent_id=agent.id,
                enabled=True,
                last_linked_at=datetime.now(tz=UTC),
                last_link_path=str(link_path),
                link_mode=prior_mode or infer_link_mode(link_path),
            )
            await reconcile_external_registration(service, agent)
            return binding
        if not force:
            raise TargetConflict(str(link_path), status.drift.value)
        # Backup + remove. Microseconds in the suffix, plus a uniquifying
        # counter, so colliding force=True enables (same microsecond, a
        # retry, or a pre-existing backup) never clobber an earlier backup.
        stamp = int(datetime.now(tz=UTC).timestamp() * 1_000_000)
        backup = link_path.with_name(f"{link_path.name}.coffer-backup-{stamp}")
        counter = 0
        while backup.exists() or backup.is_symlink():
            counter += 1
            backup = link_path.with_name(f"{link_path.name}.coffer-backup-{stamp}-{counter}")
        link_path.rename(backup)

    # Ensure the agent's skill_dir parent is in place.
    target_dir.mkdir(parents=True, exist_ok=True)

    mode = service._sync.make_directory_link(target=master, link=link_path)
    binding = await service._bindings.upsert(
        skill_id=skill.id,
        agent_id=agent.id,
        enabled=True,
        last_linked_at=datetime.now(tz=UTC),
        last_link_path=str(link_path),
        link_mode=mode,
    )
    await service._audit.record(
        AuditEventType.SKILL_BOUND.value,
        ref=ResourceRef("skill", skill_name),
        actor=actor,
        details={
            "agent": agent_name,
            "link": str(link_path),
            "mode": mode.value,
        },
    )
    # EXTERNAL_DIR agents: ensure the Coffer-owned dir is registered in the
    # agent's config now that it holds a delivered skill (no-op otherwise).
    await reconcile_external_registration(service, agent)
    return binding


async def disable_skill_for_agent(
    *,
    service: SkillService,
    skill_name: str,
    agent_name: str,
    actor: str,
) -> BindingState:
    skill = await service._rs.get(ResourceRef("skill", skill_name))
    agent = await service._rs.get(ResourceRef("agent", agent_name))
    existing = await service._bindings.find(skill_id=skill.id, agent_id=agent.id)
    if existing is None:
        # Nothing was ever bound — disabling is a no-op. Don't write a
        # phantom disabled row or a spurious SKILL_UNBOUND audit event.
        return BindingState(
            skill_resource_id=skill.id,
            agent_resource_id=agent.id,
            enabled=False,
        )
    if existing.last_link_path:
        with contextlib.suppress(OSError):
            service._sync.remove_directory_link(
                pathlib.Path(existing.last_link_path), link_mode=existing.link_mode
            )
    binding = await service._bindings.upsert(
        skill_id=skill.id,
        agent_id=agent.id,
        enabled=False,
        last_link_path=None,
        link_mode=None,
    )
    await service._audit.record(
        AuditEventType.SKILL_UNBOUND.value,
        ref=ResourceRef("skill", skill_name),
        actor=actor,
        details={"agent": agent_name},
    )
    # EXTERNAL_DIR agents: deregister the Coffer-owned dir once its last
    # delivered skill is removed (no-op otherwise).
    await reconcile_external_registration(service, agent)
    return binding
