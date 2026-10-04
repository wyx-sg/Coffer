"""An agent's copy of a skill that is a folder in the way of Coffer's link.

Spec skill-manager "Resolve a folder in the way of a skill's link" and "Refuse
deleting a skill whose copy Coffer did not make". Delivery never overwrites a
real folder at an agent's link path (that is drift kind
``replaced_with_regular``, left alone by every pass); these are the two
choices a person confirms instead, after comparing the two sides:

- keep **master** — the folder is moved to ``~/.coffer/content/backup/skills/<agent>/
  <name>-<UTC stamp>/`` (never deleted) and Coffer's link is made in its place;
- keep the **agent**'s version — its files become the master (every other
  agent sees them at once through its link), then the folder is backed up the
  same way and linked.

Nothing else is touched: no other agent's copy, no other skill.
"""

from __future__ import annotations

import os
import pathlib
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from coffer.application.skill import binding_ops
from coffer.application.skill.builtin_seed import is_builtin
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceProtected, SkillValidationError
from coffer.domain.resource import Resource
from coffer.domain.skill.binding import BindingState, LinkMode
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.copy_errors import SkillCopyNotDiffering, SkillCopyNotOurs
from coffer.domain.skill.drift import DriftKind
from coffer.domain.skill.folder_diff import FileChange, diff_folders
from coffer.domain.skill.validator import ValidationOk, validate_skill_folder

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService

Keep = Literal["master", "agent"]


@dataclass(frozen=True)
class CopyCompare:
    """One agent's folder in the way, compared with master (master → folder)."""

    skill: Resource
    agent: Resource
    path: pathlib.Path
    kind: DriftKind
    modified_at: datetime | None
    changes: list[FileChange]


def _link_for(
    service: SkillService, skill: Resource, agent: Resource, b: BindingState | None
) -> pathlib.Path:
    if b is not None and b.last_link_path:
        return pathlib.Path(b.last_link_path)
    return service._resolve_agent_skill_dir(agent) / skill.name


def _is_foreign(
    service: SkillService, link: pathlib.Path, master: pathlib.Path, mode: LinkMode | None
) -> bool:
    if not (link.exists() or link.is_symlink()):
        return False
    status = service._sync.classify_target(link=link, expected_master=master, link_mode=mode)
    return status.drift is DriftKind.REPLACED_WITH_REGULAR


def _newest_mtime(folder: pathlib.Path) -> datetime | None:
    newest: float | None = None
    for root, _dirs, files in os.walk(folder):
        for f in files:
            try:
                m = (pathlib.Path(root) / f).stat().st_mtime
            except OSError:
                continue
            newest = m if newest is None else max(newest, m)
    return datetime.fromtimestamp(newest, tz=UTC) if newest is not None else None


async def _pair(
    service: SkillService, skill_uid: str, agent_uid: str
) -> tuple[Resource, Resource, pathlib.Path, pathlib.Path]:
    skill = await service.get_skill(skill_uid)
    agent = await service._rs.get(agent_uid)
    binding = await service._bindings.find(skill_uid=skill.uid, agent_uid=agent.uid)
    link = _link_for(service, skill, agent, binding)
    master = pathlib.Path(service._store.paths_for(skill.name).folder)
    if not _is_foreign(service, link, master, binding.link_mode if binding else None):
        raise SkillCopyNotDiffering(skill.name, agent.name)
    return skill, agent, link, master


async def compare(service: SkillService, *, skill_uid: str, agent_uid: str) -> CopyCompare:
    """What the agent's folder has that master does not (read-only)."""
    skill, agent, link, master = await _pair(service, skill_uid, agent_uid)
    return CopyCompare(
        skill=skill,
        agent=agent,
        path=link,
        kind=DriftKind.REPLACED_WITH_REGULAR,
        modified_at=_newest_mtime(link),
        changes=[c for c in diff_folders(master, link) if c.path != ".coffer.meta.json"],
    )


def _backup(
    service: SkillService, agent: Resource, name: str, folder: pathlib.Path
) -> pathlib.Path:
    """Move ``folder`` under ``~/.coffer/content/backup/skills/<agent>/`` — never delete it."""
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S%fZ")
    root = pathlib.Path(service._store.backup_root) / agent.name
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{name}-{stamp}"
    shutil.move(str(folder), str(dest))
    return dest


async def _adopt_into_master(
    service: SkillService, skill: Resource, folder: pathlib.Path, actor: str
) -> Resource:
    result = validate_skill_folder(folder, size_limit_bytes=service._size_limit)
    if not isinstance(result, ValidationOk):
        raise SkillValidationError(result.reason)
    if result.frontmatter.name != skill.name:
        raise SkillValidationError(
            "name_mismatch",
            {"expected": skill.name, "found": result.frontmatter.name},
        )
    cfg = SkillConfig.model_validate(skill.config)
    service._store.atomic_replace(
        src=folder,
        name=skill.name,
        meta={"name": skill.name, "version_hash": result.skill_md_sha256},
    )
    cfg = cfg.model_copy(
        update={
            "skill_md_description": result.frontmatter.description,
            "version_hash": result.skill_md_sha256,
        }
    )
    return await service._rs.update_config(
        skill.uid,
        new_config=cfg.model_dump(mode="json"),
        actor=actor,
        description=result.frontmatter.description,
        allow_lifecycle_kind=True,  # the master folder was replaced above
    )


async def resolve(
    service: SkillService, *, skill_uid: str, agent_uid: str, keep: Keep, actor: str
) -> Resource:
    """Keep master or the agent's version, then link the agent to master again."""
    skill = await service.get_skill(skill_uid)
    if is_builtin(skill.config):
        raise ResourceProtected(
            f"skill {skill.name}",
            "Coffer writes this skill itself at every start; turn it off instead",
        )
    skill, agent, link, _master = await _pair(service, skill_uid, agent_uid)
    if keep == "agent":
        skill = await _adopt_into_master(service, skill, link, actor)
    backup = _backup(service, agent, skill.name, link)
    await binding_ops.deliver(service, skill=skill, agent=agent, link=link)
    await service._audit.record(
        (AuditEventType.SKILL_ADOPTED if keep == "agent" else AuditEventType.SKILL_RELINKED).value,
        resource=skill,
        actor=actor,
        details={"agent": agent.name, "link": str(link), "backup": str(backup), "kept": keep},
    )
    return skill


@dataclass(frozen=True)
class KeptCopy:
    """An agent's folder a delete left alone because it is not Coffer's link."""

    agent_name: str
    path: str


async def refuse_foreign_copies(
    service: SkillService, skill: Resource, *, keep: list[KeptCopy] | None = None
) -> None:
    """Refuse a delete that would leave (or wipe) a folder Coffer did not make.

    With ``keep`` given the delete goes ahead instead: each such folder is
    appended to ``keep`` and left where it is (spec skill-manager "Refuse
    deleting a skill whose copy Coffer did not make")."""
    master = pathlib.Path(service._store.paths_for(skill.name).folder)
    agents = {a.uid: a for a in await service.list_agents()}
    for b in await service._bindings.list_for_skill(skill.uid):
        if not b.enabled or not b.last_link_path:
            continue
        link = pathlib.Path(b.last_link_path)
        if _is_foreign(service, link, master, b.link_mode):
            agent = agents.get(b.agent_uid)
            name = agent.name if agent else ""
            if keep is None:
                raise SkillCopyNotOurs(skill.name, str(link), name)
            keep.append(KeptCopy(name, str(link)))


__all__ = ["CopyCompare", "KeptCopy", "compare", "refuse_foreign_copies", "resolve"]
