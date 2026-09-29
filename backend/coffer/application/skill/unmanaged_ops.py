"""Unmanaged-skill scan / adopt / delete helpers for SkillService (see
"List unmanaged skills in an agent's skill locations").

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
import pathlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource
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


@dataclass(frozen=True)
class UnmanagedDetail:
    """One unmanaged skill as its detail page shows it.

    ``folder`` is the entry's path as found in the agent's location — for a
    foreign link, the link itself; the file readers resolve it, so a preview
    shows what the agent would load and stays confined to that folder.
    """

    view: UnmanagedView
    description: str | None
    folder: pathlib.Path


def _label(index: int) -> str:
    return _LOC_PRIMARY if index == 0 else _LOC_SECONDARY


def _scan(service: SkillService, agent: Resource) -> list[tuple[str, UnmanagedSkill]]:
    """(location_label, UnmanagedSkill) pairs across the agent's locations."""
    # Narrow the optional deps for the type checker; callers go through
    # SkillService._require_unmanaged_deps first, so this never trips.
    resolver = service._resolve_agent_scan_locations
    scanner = service._workspace_scan
    if resolver is None or scanner is None:  # pragma: no cover — guarded upstream
        raise RuntimeError("workspace scan dependencies are not wired")
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


def _view(service: SkillService, label: str, u: UnmanagedSkill) -> tuple[UnmanagedView, str | None]:
    """The API view of one scanned entry, plus its SKILL.md description.

    The description is only known when the folder validates — an invalid
    folder's frontmatter is exactly what could not be read — so it is ``None``
    whenever ``valid`` is false.
    """
    description: str | None = None
    if u.foreign_link:
        valid, reason = False, FOREIGN_LINK_REASON
    else:
        result = validate_skill_folder(u.path, size_limit_bytes=service._size_limit)
        if isinstance(result, ValidationOk):
            valid, reason = True, None
            description = result.frontmatter.description
        else:
            valid, reason = False, result.reason
    view = UnmanagedView(
        name=u.name,
        path=str(u.path),
        location=label,
        valid=valid,
        reason=reason,
        foreign_link=u.foreign_link,
    )
    return view, description


async def list_unmanaged(*, service: SkillService, agent_uid: str) -> list[UnmanagedView]:
    """Discover unmanaged skills across the agent's scan locations."""
    agent = await service._rs.get(agent_uid)
    return [_view(service, label, u)[0] for label, u in _scan(service, agent)]


async def get_unmanaged(
    *, service: SkillService, agent_uid: str, skill_name: str, location: str
) -> UnmanagedDetail:
    """One unmanaged entry, found by the same scan the list runs (see "Preview
    an unmanaged skill read-only").

    Looking the folder up through the scan — rather than joining the name onto
    a location path — is what confines every read to a folder the list would
    have shown: a ``..`` or a slash in ``skill_name`` simply matches no entry
    and is a 404, and a managed link is never an unmanaged entry to begin with.
    """
    agent = await service._rs.get(agent_uid)
    entry = _find(_scan(service, agent), skill_name=skill_name, location=location)
    view, description = _view(service, location, entry)
    return UnmanagedDetail(view=view, description=description, folder=entry.path)


async def adopt_unmanaged(
    *,
    service: SkillService,
    agent_uid: str,
    skill_name: str,
    location: str,
    actor: str,
) -> Resource:
    """Adopt an unmanaged skill folder into the master store.

    Copy into master + register + deliver (via ``register_from_validated``),
    then remove the original folder and deliver the managed link to the
    agent's canonical delivery location ``<config_dir>/skills/<name>`` —
    in-place replacement when adopting from there, consolidation when
    adopting from ``~/.agents/skills`` (the original is removed; Codex reads
    both locations, so the skill stays visible). See spec skill-manager "Adopt an unmanaged skill".
    The delivery pass ``register_from_validated`` asks for leaves THIS agent
    alone while the original folder still occupies the link path (foreign
    content is never clobbered) — that is why the rmtree happens first and
    the link is made after it, directly: adoption links in place even into a
    disabled agent, which the reconciler would not.
    """
    from coffer.application.skill.lifecycle_ops import register_from_validated

    agent = await service._rs.get(agent_uid)
    # ``skill_name`` here is a DIRECTORY name found on disk, not a resource
    # label: an unmanaged skill has no row, so there is no uid to address it
    # by until adoption mints one.
    found = _scan(service, agent)
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
    from coffer.application.skill.binding_ops import deliver

    link = service._resolve_agent_skill_dir(agent) / resource.name
    written = await deliver(service, skill=resource, agent=agent, link=link)
    if written.created is not None:
        # Adoption is the one delivery made outside the reconciler (it links
        # in place even into a disabled agent), so it records its own event.
        await service._audit.record(
            AuditEventType.SKILL_BOUND.value,
            resource=resource,
            actor=actor,
            details={
                "agent": agent.name,
                "link": str(link),
                "mode": written.mode.value if written.mode else None,
            },
        )
    return resource


async def delete_unmanaged(
    *,
    service: SkillService,
    agent_uid: str,
    skill_name: str,
    location: str,
    actor: str,
) -> None:
    """Remove an unmanaged entry from the agent's workspace.

    A foreign symlink is unlinked (its target is never touched); a plain
    directory is removed recursively.
    """
    agent = await service._rs.get(agent_uid)
    found = _scan(service, agent)
    entry = _find(found, skill_name=skill_name, location=location)
    if entry.path.is_symlink():
        entry.path.unlink()
    else:
        service._rmtree(entry.path)
    # No ``resource=``: unmanaged entries have no resource row at all, so the
    # event is recorded against nothing and says in its details what was
    # removed and from where.
    await service._audit.record(
        AuditEventType.SKILL_UNMANAGED_DELETED.value,
        actor=actor,
        details={
            "name": skill_name,
            "agent": agent.name,
            "path": str(entry.path),
            "location": location,
        },
    )
