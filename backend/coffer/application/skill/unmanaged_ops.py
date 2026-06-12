"""Unmanaged-skill scan / adopt / delete helpers for SkillService (FR-022).

Free functions in the ``lifecycle_ops`` style: they take the SkillService
instance and reach into its (private) attributes — conceptually private to
the skill subpackage.

Agent scan locations come from the injected
``agent_scan_locations_resolver`` (a Callable built at the composition root
from ``AgentConfig`` + ``coffer.domain.agent.scan.scan_locations``) — never
from a direct ``domain.agent`` import, which Contract 5c forbids.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.skill.scan import UnmanagedSkill, classify
from coffer.domain.skill.source import LocalImportSource
from coffer.domain.skill.validator import ValidationOk, validate_skill_folder
from coffer.domain.workspace_errors import UnmanagedSkillInvalid, UnmanagedSkillNotFound

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService

logger = logging.getLogger(__name__)

FOREIGN_LINK_REASON = "symlink points outside the master store"

# Location labels by position in the resolver's ordered list: index 0 is
# always `<config_dir>/skills`; any later entry is the agent product's
# secondary standard location (today: Codex's `~/.agents/skills`).
_LOC_PRIMARY = "skills"
_LOC_SECONDARY = "agents_dir"


@dataclass(frozen=True)
class UnmanagedView:
    """One unmanaged skill as surfaced to the API / UI."""

    name: str
    path: str
    location: str  # "skills" | "agents_dir"
    valid: bool
    reason: str | None
    foreign_link: bool


def _label(index: int) -> str:
    return _LOC_PRIMARY if index == 0 else _LOC_SECONDARY


async def _scan(service: SkillService, agent_name: str) -> list[tuple[str, UnmanagedSkill]]:
    """(location_label, UnmanagedSkill) pairs across the agent's locations."""
    # Narrow the optional deps for the type checker; callers go through
    # SkillService._require_unmanaged_deps first, so this never trips.
    resolver = service._resolve_agent_scan_locations
    scanner = service._workspace_scan
    if resolver is None or scanner is None:  # pragma: no cover — guarded upstream
        raise RuntimeError("workspace scan dependencies are not wired")
    agent = await service._rs.get(ResourceRef("agent", agent_name))
    locations = resolver(agent)
    master_root = service._store.root
    out: list[tuple[str, UnmanagedSkill]] = []
    for i, loc in enumerate(locations):
        entries = scanner.scan_dir(loc)
        for u in classify(entries, master_root=master_root):
            out.append((_label(i), u))
    return out


def _find(
    found: list[tuple[str, UnmanagedSkill]], *, skill_name: str, location: str
) -> UnmanagedSkill:
    for label, u in found:
        if u.name == skill_name and label == location:
            return u
    raise UnmanagedSkillNotFound(skill_name)


async def list_unmanaged(*, service: SkillService, agent_name: str) -> list[UnmanagedView]:
    """Discover unmanaged skills across the agent's scan locations."""
    views: list[UnmanagedView] = []
    for label, u in await _scan(service, agent_name):
        if u.foreign_link:
            valid, reason = False, FOREIGN_LINK_REASON
        else:
            result = validate_skill_folder(u.path, size_limit_bytes=service._size_limit)
            if isinstance(result, ValidationOk):
                valid, reason = True, None
            else:
                valid, reason = False, result.reason
        views.append(
            UnmanagedView(
                name=u.name,
                path=str(u.path),
                location=label,
                valid=valid,
                reason=reason,
                foreign_link=u.foreign_link,
            )
        )
    return views


async def adopt_unmanaged(
    *,
    service: SkillService,
    agent_name: str,
    skill_name: str,
    location: str,
    actor: str,
) -> Resource:
    """Adopt an unmanaged skill folder into the master store.

    Copy into master + register + auto-bind (via ``register_from_validated``),
    then remove the original folder and deliver the managed link to the
    agent's canonical delivery location ``<config_dir>/skills/<name>`` —
    in-place replacement when adopting from there, consolidation when
    adopting from ``~/.agents/skills`` (the original is removed; Codex reads
    both locations, so the skill stays visible). See spec 005 FR-023.
    Auto-bind inside ``register_from_validated`` skips THIS agent with a
    TargetConflict while the original folder still occupies the link path —
    that is why the rmtree happens first and ``enable_for`` runs after it.
    """
    from coffer.application.skill.lifecycle_ops import register_from_validated

    found = await _scan(service, agent_name)
    entry = _find(found, skill_name=skill_name, location=location)
    if entry.foreign_link:
        raise UnmanagedSkillInvalid(skill_name, FOREIGN_LINK_REASON)
    result = validate_skill_folder(entry.path, size_limit_bytes=service._size_limit)
    if not isinstance(result, ValidationOk):
        raise UnmanagedSkillInvalid(skill_name, result.reason)

    resource = await register_from_validated(
        service=service,
        src=entry.path,
        validation=result,
        source_meta=LocalImportSource(original_path=str(entry.path)),
        event=AuditEventType.SKILL_ADOPTED,
        actor=actor,
    )

    # Post-registration delivery. Failures past this point do NOT roll back
    # the resource — the master copy is good. If rmtree fails, the original
    # folder may linger; a re-adoption attempt then hits ResourceAlreadyExists
    # (acceptable: the skill IS registered, the leftover is cleanable via
    # delete_unmanaged). If the frontmatter name differs from the folder
    # name, the managed link lands under the FRONTMATTER name while the old
    # folder (under its own name) is still removed — the folder name was
    # never the skill's identity.
    service._rmtree(entry.path)
    await service.enable_for(
        skill_name=resource.name, agent_name=agent_name, force=False, actor=actor
    )
    return resource


async def delete_unmanaged(
    *,
    service: SkillService,
    agent_name: str,
    skill_name: str,
    location: str,
    actor: str,
) -> None:
    """Remove an unmanaged entry from the agent's workspace.

    A foreign symlink is unlinked (its target is never touched); a plain
    directory is removed recursively.
    """
    found = await _scan(service, agent_name)
    entry = _find(found, skill_name=skill_name, location=location)
    if entry.path.is_symlink():
        entry.path.unlink()
    else:
        service._rmtree(entry.path)
    # No ResourceRef: unmanaged entries have no resource row, and arbitrary
    # on-disk folder names may not satisfy the resource-name pattern.
    await service._audit.record(
        AuditEventType.SKILL_UNMANAGED_DELETED.value,
        actor=actor,
        details={
            "name": skill_name,
            "agent": agent_name,
            "path": str(entry.path),
            "location": location,
        },
    )
