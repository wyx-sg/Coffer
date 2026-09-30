"""Folders in the skills store that no skill claims ("Not in your library").

Spec skill-manager "Act on a folder in the skills store that no skill claims".
A folder copied into ``~/.coffer/vault/skills/`` by hand, or left behind by an
interrupted import, reaches no agent. The drift report lists it
(``orphan_master``); these are the two things a person can do with it: add
it to the library in place, or move it out of the store (to
``~/.coffer/content/backup/skills/orphans/``, never a hard delete).
"""

from __future__ import annotations

import pathlib
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.errors import SkillValidationError
from coffer.domain.resource import Resource
from coffer.domain.skill.content_hash import iter_content_files
from coffer.domain.skill.copy_errors import SkillOrphanNotFound
from coffer.domain.skill.source import LocalImportSource
from coffer.domain.skill.validator import ValidationOk, validate_skill_folder

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService


@dataclass(frozen=True)
class OrphanView:
    name: str
    path: pathlib.Path
    valid: bool
    file_count: int
    description: str | None
    message: str | None


async def _orphan_names(service: SkillService) -> list[str]:
    known = {s.name for s in await service.list_skills()}
    return list(service._store.find_orphans(known))


async def _folder(service: SkillService, name: str) -> pathlib.Path:
    if name not in await _orphan_names(service):
        raise SkillOrphanNotFound(name)
    return pathlib.Path(service._store.paths_for(name).folder)


async def list_orphans(service: SkillService) -> list[OrphanView]:
    out: list[OrphanView] = []
    for name in await _orphan_names(service):
        folder = pathlib.Path(service._store.paths_for(name).folder)
        result = validate_skill_folder(folder, size_limit_bytes=service._size_limit)
        if isinstance(result, ValidationOk):
            valid = result.frontmatter.name == name
            description: str | None = result.frontmatter.description
            message: str | None = None if valid else "name_mismatch"
        else:
            valid, description, message = False, None, result.reason
        out.append(
            OrphanView(
                name=name,
                path=folder,
                valid=valid,
                file_count=len(iter_content_files(folder)),
                description=description,
                message=message,
            )
        )
    return out


async def adopt_orphan(service: SkillService, *, name: str, actor: str) -> Resource:
    """Register the folder in place as a skill; reach defaults as a fresh import."""
    from coffer.application.skill.lifecycle_ops import register_from_validated

    folder = await _folder(service, name)
    result = validate_skill_folder(folder, size_limit_bytes=service._size_limit)
    if not isinstance(result, ValidationOk):
        raise SkillValidationError(result.reason, dict(result.details))
    if result.frontmatter.name != name:
        raise SkillValidationError(
            "name_mismatch", {"expected": name, "found": result.frontmatter.name}
        )
    return await register_from_validated(
        service=service,
        src=folder,
        validation=result,
        source_meta=LocalImportSource(original_path=str(folder)),
        event=AuditEventType.SKILL_ADOPTED,
        actor=actor,
        overwrite=True,
        audit_details={"orphan": True},
    )


async def remove_orphan(service: SkillService, *, name: str, actor: str) -> pathlib.Path:
    """Move the folder out of the store into the backup folder."""
    folder = await _folder(service, name)
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S%fZ")
    root = pathlib.Path(service._store.backup_root) / "orphans"
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{name}-{stamp}"
    shutil.move(str(folder), str(dest))
    await service._audit.record(
        AuditEventType.SKILL_UNMANAGED_DELETED.value,
        actor=actor,
        details={"name": name, "path": str(folder), "backup": str(dest), "orphan": True},
    )
    return dest


__all__ = ["OrphanView", "adopt_orphan", "list_orphans", "remove_orphan"]
