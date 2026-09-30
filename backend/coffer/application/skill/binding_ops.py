"""The writers behind one skill delivery: link + binding row, and their undo.

Each writer performs the on-disk link change and the ``skill_agent_bindings``
row that records it, and records **no** audit event: the caller decides what
the write means. The reconcile target (``link_reconcile``) hands the event back
to the reconciler, which records it and runs :func:`undo` if recording fails
(ADR one-level-triggered-reconciler-compares-parameters, "audit follows the
write"); adoption, the one explicit write outside the reconciler, records its
own.

Every writer returns a :class:`LinkWrite` describing what it replaced, so
:func:`undo` can put it back: the link it created is removed, a link it moved
aside is renamed back, a link it removed is recreated, and the binding row is
restored to its prior state.

Conceptually private to the skill subpackage, like ``lifecycle_ops``: these
take the ``SkillService`` and reach into its attributes.
"""

from __future__ import annotations

import contextlib
import pathlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from coffer.domain.resource import Resource
from coffer.domain.skill.binding import BindingState, LinkMode

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService


@dataclass(frozen=True)
class LinkWrite:
    """What one writer did, in enough detail to undo it."""

    skill: Resource
    agent: Resource
    #: The binding row before the write (``None``: there was none).
    prior: BindingState | None
    #: The link path the write created, if it created one.
    created: pathlib.Path | None = None
    #: How the created (or adopted) link is realised.
    mode: LinkMode | None = None
    #: Where a tampered link was renamed aside to, and where it came from.
    backup: pathlib.Path | None = None
    backed_up_from: pathlib.Path | None = None
    #: A correct link the write removed (reclaim, or the old path of a move).
    removed: pathlib.Path | None = None


def _backup_path(link: pathlib.Path) -> pathlib.Path:
    """``<link>.coffer-backup-<µs>`` — with a counter, so two backups in the
    same microsecond (or a pre-existing one) never clobber each other."""
    stamp = int(datetime.now(tz=UTC).timestamp() * 1_000_000)
    backup = link.with_name(f"{link.name}.coffer-backup-{stamp}")
    counter = 0
    while backup.exists() or backup.is_symlink():
        counter += 1
        backup = link.with_name(f"{link.name}.coffer-backup-{stamp}-{counter}")
    return backup


def _is_correct_link(
    service: SkillService,
    link: pathlib.Path,
    master: pathlib.Path,
    mode: LinkMode | None = None,
) -> bool:
    if not (link.exists() or link.is_symlink()):
        return False
    status = service._sync.classify_target(link=link, expected_master=master, link_mode=mode)
    return status.drift is None


async def _record(
    service: SkillService,
    skill: Resource,
    agent: Resource,
    link: pathlib.Path,
    mode: LinkMode | None,
) -> None:
    await service._bindings.upsert(
        skill_uid=skill.uid,
        agent_uid=agent.uid,
        enabled=True,
        last_linked_at=datetime.now(tz=UTC),
        last_link_path=str(link),
        link_mode=mode,
    )


async def deliver(
    service: SkillService,
    *,
    skill: Resource,
    agent: Resource,
    link: pathlib.Path,
    back_up_existing: bool = False,
) -> LinkWrite:
    """Link ``link`` to the skill's master folder and record the binding.

    A correct link already at ``link`` is adopted as it is (only the row is
    written). ``back_up_existing`` renames whatever else sits there aside to
    ``<link>.coffer-backup-<ts>`` first — the tampered-link repair; without it
    an occupied path raises ``FileExistsError`` and nothing is written.
    """
    master = service._store.paths_for(skill.name).folder
    prior = await service._bindings.find(skill_uid=skill.uid, agent_uid=agent.uid)
    if _is_correct_link(service, link, master):
        mode = (prior.link_mode if prior else None) or service._sync.infer_link_mode(link)
        await _record(service, skill, agent, link, mode)
        return LinkWrite(skill, agent, prior, mode=mode)
    backup: pathlib.Path | None = None
    if (link.exists() or link.is_symlink()) and back_up_existing:
        backup = _backup_path(link)
        link.rename(backup)
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = service._sync.make_directory_link(target=master, link=link)
    except Exception:
        if backup is not None:
            backup.rename(link)
        raise
    written = LinkWrite(
        skill, agent, prior, created=link, mode=mode, backup=backup, backed_up_from=link
    )
    try:
        await _record(service, skill, agent, link, mode)
    except Exception:
        await undo(service, written)
        raise
    return written


async def relink(
    service: SkillService,
    *,
    skill: Resource,
    agent: Resource,
    old_link: pathlib.Path,
    new_link: pathlib.Path,
) -> LinkWrite:
    """Move a delivery to the agent's new skills directory: the new link is
    made first (or a correct one adopted), the old one removed second."""
    master = service._store.paths_for(skill.name).folder
    old_was_correct = _is_correct_link(service, old_link, master)
    written = await deliver(service, skill=skill, agent=agent, link=new_link)
    prior = written.prior
    with contextlib.suppress(OSError):
        service._sync.remove_directory_link(old_link, link_mode=prior.link_mode if prior else None)
    removed = old_link if old_was_correct and not old_link.exists() else None
    return LinkWrite(
        skill, agent, prior, created=written.created, mode=written.mode, removed=removed
    )


async def reclaim(service: SkillService, *, skill: Resource, agent: Resource) -> LinkWrite:
    """Remove the delivered link (never foreign content: see
    ``SyncEngine.remove_directory_link``) and mark the binding row spent."""
    prior = await service._bindings.find(skill_uid=skill.uid, agent_uid=agent.uid)
    removed: pathlib.Path | None = None
    if prior is not None and prior.last_link_path:
        path = pathlib.Path(prior.last_link_path)
        master = service._store.paths_for(skill.name).folder
        was_correct = _is_correct_link(service, path, master, prior.link_mode)
        with contextlib.suppress(OSError):
            service._sync.remove_directory_link(path, link_mode=prior.link_mode)
        if was_correct and not path.exists():
            removed = path
    await service._bindings.upsert(
        skill_uid=skill.uid,
        agent_uid=agent.uid,
        enabled=False,
        last_link_path=None,
        link_mode=None,
    )
    return LinkWrite(skill, agent, prior, removed=removed)


async def undo(service: SkillService, write: LinkWrite) -> None:
    """Put back what ``write`` replaced: remove the link it created, move a
    backup back, recreate a correct link it removed, restore the row."""
    if write.created is not None:
        with contextlib.suppress(OSError):
            service._sync.remove_directory_link(write.created, link_mode=write.mode)
    if write.backup is not None and write.backed_up_from is not None:
        write.backup.rename(write.backed_up_from)
    if write.removed is not None and not (write.removed.exists() or write.removed.is_symlink()):
        master = service._store.paths_for(write.skill.name).folder
        with contextlib.suppress(OSError):
            service._sync.make_directory_link(target=master, link=write.removed)
    prior = write.prior
    if prior is None:
        await service._bindings.delete(write.skill.uid, write.agent.uid)
        return
    await service._bindings.upsert(
        skill_uid=write.skill.uid,
        agent_uid=write.agent.uid,
        enabled=prior.enabled,
        last_linked_at=prior.last_linked_at,
        last_link_path=prior.last_link_path,
        link_mode=prior.link_mode,
    )


__all__ = ["LinkWrite", "deliver", "reclaim", "relink", "undo"]
