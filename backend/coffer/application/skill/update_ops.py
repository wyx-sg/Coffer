"""Update + rename helpers for SkillService.

Extracted to keep `service.py` under the file-size limit. These free
functions take the SkillService instance and reach into its (private)
attributes — they are conceptually private to the skill subpackage.
"""

from __future__ import annotations

import contextlib
import logging
import pathlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.errors import SkillNameMismatch
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.skill.binding import LinkMode
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.validator import ValidationOk

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService, UpdateOutcome

logger = logging.getLogger(__name__)


async def apply_update(
    *,
    service: SkillService,
    existing: Resource,
    cfg: SkillConfig,
    validation: ValidationOk,
    src: pathlib.Path,
    allow_rename: bool,
    actor: str,
) -> UpdateOutcome:
    from coffer.application.skill.service import UpdateOutcome  # local to avoid cycle

    now = datetime.now(tz=UTC)
    new_name = validation.frontmatter.name
    renamed = new_name != existing.name
    if renamed and not allow_rename:
        raise SkillNameMismatch(existing.name, new_name)

    if validation.skill_md_sha256 == cfg.version_hash and not renamed:
        await service._audit.record(
            AuditEventType.SKILL_UPDATE_NOOP.value,
            ref=existing.ref,
            actor=actor,
            details={"version_hash": cfg.version_hash},
        )
        return UpdateOutcome(skill=existing, changed=False)

    old_name = existing.name
    new_cfg = cfg.model_copy(
        update={
            "skill_md_name": new_name,
            "skill_md_description": validation.frontmatter.description,
            "version_hash": validation.skill_md_sha256,
            "last_synced_from_source_at": now,
        }
    )

    if renamed:
        await _rename_master_and_bindings(
            service=service,
            old_name=old_name,
            new_name=new_name,
            src=src,
            new_cfg=new_cfg,
            actor=actor,
        )
    else:
        service._store.atomic_replace(
            src=src,
            name=old_name,
            meta={
                "name": old_name,
                "source": new_cfg.source.model_dump(mode="json"),
                "updated_at": now,
                "version_hash": validation.skill_md_sha256,
            },
        )

    ref = ResourceRef("skill", new_name if renamed else old_name)
    updated = await service._rs.update_config(
        ref,
        new_config=new_cfg.model_dump(mode="json"),
        actor=actor,
    )
    await service._audit.record(
        AuditEventType.SKILL_UPDATED.value,
        ref=ref,
        actor=actor,
        details={
            "before_hash": cfg.version_hash,
            "after_hash": validation.skill_md_sha256,
            "renamed_from": old_name if renamed else None,
        },
    )
    return UpdateOutcome(skill=updated, changed=True, renamed_from=old_name if renamed else None)


async def _rename_master_and_bindings(
    *,
    service: SkillService,
    old_name: str,
    new_name: str,
    src: pathlib.Path,
    new_cfg: SkillConfig,
    actor: str,
) -> None:
    # Atomicity model: register the NEW resource BEFORE deleting the old one,
    # so a register failure can never leave the skill with neither row (the
    # old "vanish" bug). Order of operations:
    #   1. stage the new master (nothing else touched yet → failure is clean)
    #   2. register the new resource row (roll back the staged master on error)
    #   3. re-point each binding to the new name: create the new link, upsert
    #      the row under the new id, then remove the old link
    #   4. delete the old resource (its on_delete hook cascades the old binding
    #      rows + old master; old links were already removed in step 3, and the
    #      teardown is idempotent)
    old_resource = await service._rs.get(ResourceRef("skill", old_name))
    bindings = await service._bindings.list_for_skill(old_resource.id)

    # 1) Stage the new master.
    service._store.copy_in(
        src=src,
        name=new_name,
        meta={
            "name": new_name,
            "source": new_cfg.source.model_dump(mode="json"),
            "renamed_from": old_name,
            "version_hash": new_cfg.version_hash,
        },
    )

    # 2) Register the new resource before removing the old one.
    try:
        new_resource = await service._rs.register(
            kind="skill",
            name=new_name,
            config=new_cfg.model_dump(mode="json"),
            description=new_cfg.skill_md_description,
            actor=actor,
        )
    except Exception:
        service._store.delete(new_name)  # roll back the staged master
        raise

    # 3) Re-point bindings. Always upsert the row (even when the new link path
    #    already exists) so no binding is silently dropped.
    new_paths = service._store.paths_for(new_name)
    now = datetime.now(tz=UTC)
    for b in bindings:
        agent = await service._get_agent_by_id(b.agent_resource_id)
        if agent is None:
            continue
        new_link = service._resolve_agent_skill_dir(agent) / new_name
        try:
            if new_link.exists() or new_link.is_symlink():
                # Something already at the new path. Only adopt it if it's a
                # correct Coffer link to the new master; if it's FOREIGN
                # content, record link_mode=None so teardown never rmtrees the
                # user's directory (and verify surfaces the drift).
                status = service._sync.classify_target(
                    link=new_link, expected_master=new_paths.folder, link_mode=b.link_mode
                )
                mode = (b.link_mode or LinkMode.SYMLINK) if status.drift is None else None
            else:
                mode = service._sync.make_directory_link(target=new_paths.folder, link=new_link)
            await service._bindings.upsert(
                skill_id=new_resource.id,
                agent_id=agent.id,
                enabled=b.enabled,
                last_linked_at=now,
                last_link_path=str(new_link),
                link_mode=mode,
            )
        except OSError as e:
            # Don't abort the whole rename for one agent, but don't drop it
            # silently either — surface which agent didn't get re-linked.
            logger.warning(
                "rename re-link of skill %r for agent %r skipped: %s", new_name, agent.name, e
            )
        if b.last_link_path:
            with contextlib.suppress(OSError):
                service._sync.remove_directory_link(
                    pathlib.Path(b.last_link_path), link_mode=b.link_mode
                )

    # 4) Delete the old resource (cascades old binding rows + old master).
    await service._rs.delete(ResourceRef("skill", old_name), actor=actor)
    await service._audit.record(
        AuditEventType.SKILL_RENAMED.value,
        ref=ResourceRef("skill", new_name),
        actor=actor,
        details={"from": old_name, "to": new_name},
    )
