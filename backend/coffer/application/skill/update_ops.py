"""Update + rename helpers for SkillService.

Extracted to keep `service.py` under the file-size limit. These free
functions take the SkillService instance and reach into its (private)
attributes — they are conceptually private to the skill subpackage.
"""

from __future__ import annotations

import contextlib
import pathlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.errors import SkillNameMismatch
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.validator import ValidationOk

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService, UpdateOutcome


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
    # Partial-failure model: if ``copy_in(new_name)`` raises (disk full,
    # name collision, OS error), we have already torn down the per-agent
    # symlinks pointing at the old master — but the old master folder
    # itself is still on disk, so we rebuild the symlinks against it and
    # let the caller surface the original error. The DB rows for bindings
    # are untouched at that point (we only re-create them AFTER the new
    # master is staged), so the row state stays consistent with the
    # re-pointed symlinks.
    old_resource = await service._rs.get(ResourceRef("skill", old_name))
    bindings = await service._bindings.list_for_skill(old_resource.id)
    old_master = service._store.paths_for(old_name).folder
    for b in bindings:
        if b.last_link_path:
            with contextlib.suppress(OSError):
                service._sync.remove_directory_link(pathlib.Path(b.last_link_path))

    try:
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
    except Exception:
        # Best-effort rollback: rebuild symlinks against the still-present
        # old master so users aren't left with bindings that point at
        # nothing. Each rebuild is also best-effort — a failure here is
        # logged via verify drift on the next run.
        for b in bindings:
            if b.last_link_path:
                with contextlib.suppress(OSError):
                    service._sync.make_directory_link(
                        target=old_master, link=pathlib.Path(b.last_link_path)
                    )
        raise
    service._store.delete(old_name)
    await service._audit.record(
        AuditEventType.SKILL_RENAMED.value,
        ref=ResourceRef("skill", new_name),
        actor=actor,
        details={"from": old_name, "to": new_name},
    )
    # ResourceService has no rename op; emulate via delete+register and
    # then re-create bindings against the new skill_resource_id.
    await service._rs.delete(ResourceRef("skill", old_name), actor=actor)
    new_resource = await service._rs.register(
        kind="skill",
        name=new_name,
        config=new_cfg.model_dump(mode="json"),
        description=new_cfg.skill_md_description,
        actor=actor,
    )
    new_paths = service._store.paths_for(new_name)
    for b in bindings:
        agent = await service._get_agent_by_id(b.agent_resource_id)
        if agent is None:
            continue
        try:
            link_path = service._resolve_agent_skill_dir(agent) / new_name
            if link_path.exists() or link_path.is_symlink():
                continue
            mode = service._sync.make_directory_link(target=new_paths.folder, link=link_path)
            await service._bindings.upsert(
                skill_id=new_resource.id,
                agent_id=agent.id,
                enabled=b.enabled,
                last_linked_at=datetime.now(tz=UTC),
                last_link_path=str(link_path),
                link_mode=mode,
            )
        except OSError:
            continue
