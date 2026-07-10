"""Import / auto-bind / relink helpers for SkillService.

Extracted to keep ``service.py`` under the file-size limit. Like
``binding_ops.py`` these are free functions that take the SkillService
instance and reach into its (private) attributes — they are conceptually
private to the skill subpackage.
"""

from __future__ import annotations

import contextlib
import logging
import pathlib
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from coffer.application.skill.delivery_ops import (
    delivers_skill_folders,
    reconcile_external_registration,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import CofferError, ResourceAlreadyExists
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.scope import agent_in_scope, machine_in_scope
from coffer.domain.skill.binding import LinkMode
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.source import LocalImportSource
from coffer.domain.skill.validator import ValidationOk

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService

logger = logging.getLogger(__name__)


def infer_link_mode(link: pathlib.Path) -> LinkMode:
    """Best-effort: what kind of link is actually on disk at `link`?

    Used when a target is already correctly linked but no prior binding row
    recorded the mode, so a junction/copy-fallback isn't mislabelled SYMLINK.
    Stdlib-only (no infrastructure import — Contract 2).
    """
    if link.is_symlink():
        return LinkMode.SYMLINK
    if sys.platform == "win32" and link.is_dir():
        import os

        try:
            attr = getattr(os.lstat(link), "st_file_attributes", 0)
        except OSError:
            attr = 0
        # FILE_ATTRIBUTE_REPARSE_POINT (0x400) marks a junction.
        return LinkMode.JUNCTION if attr & 0x400 else LinkMode.COPY_FALLBACK
    return LinkMode.COPY_FALLBACK


async def register_from_validated(
    *,
    service: SkillService,
    src: pathlib.Path,
    validation: ValidationOk,
    source_meta: LocalImportSource,
    event: AuditEventType,
    actor: str,
    overwrite: bool = False,
) -> Resource:
    name = validation.frontmatter.name
    # Duplicate check before copying any bytes.
    existing = await service._rs.list(kind="skill")
    name_taken = any(r.name == name for r in existing) or service._store.exists(name)
    if name_taken and not overwrite:
        raise ResourceAlreadyExists("skill", name)

    now = datetime.now(tz=UTC)
    cfg = SkillConfig(
        source=source_meta,
        skill_md_name=name,
        skill_md_description=validation.frontmatter.description,
        version_hash=validation.skill_md_sha256,
        last_synced_from_source_at=now,
    )
    meta = {
        "name": name,
        "source": source_meta.model_dump(mode="json"),
        "imported_at": now,
        "version_hash": validation.skill_md_sha256,
    }

    row_exists = any(r.name == name for r in existing)
    if name_taken:
        # Overwrite path: swap the master folder in place (atomic_replace also
        # covers an orphan master folder with no row — DriftKind.ORPHAN_MASTER).
        service._store.atomic_replace(src=src, name=name, meta=meta)
        if row_exists:
            # Update the existing row, preserving its id + per-agent bindings +
            # delivered symlinks (the master folder path is unchanged).
            r = await service._rs.update_config(
                ResourceRef("skill", name),
                new_config=cfg.model_dump(mode="json"),
                actor=actor,
                description=validation.frontmatter.description,
                allow_lifecycle_kind=True,  # CODE-REG: master folder replaced above
            )
            audit_event = AuditEventType.SKILL_UPDATED
        else:
            # Orphan master folder (content present, no row): register the row
            # now so we don't crash on update_config's missing-row lookup.
            r = await service._rs.register(
                kind="skill",
                name=name,
                config=cfg.model_dump(mode="json"),
                description=validation.frontmatter.description,
                actor=actor,
                allow_lifecycle_kind=True,  # CODE-REG: master folder replaced above
            )
            audit_event = event
    else:
        # Fresh import path: copy master folder in, register Resource row.
        service._store.copy_in(src=src, name=name, meta=meta)
        try:
            r = await service._rs.register(
                kind="skill",
                name=name,
                config=cfg.model_dump(mode="json"),
                description=validation.frontmatter.description,
                actor=actor,
                allow_lifecycle_kind=True,  # CODE-REG: master folder created above
            )
        except Exception:
            # Best-effort rollback of master
            service._store.delete(name)
            raise
        audit_event = event
        # Auto-bind for every enabled, following agent (FR-025).
        # On overwrite the skill is already bound; skip auto-bind to avoid
        # disturbing existing bindings.
        await auto_bind_all(service=service, skill=r, actor=actor)

    await service._audit.record(
        audit_event.value,
        ref=ResourceRef("skill", name),
        actor=actor,
        details={"version_hash": validation.skill_md_sha256},
    )
    return r


async def auto_bind_all(*, service: SkillService, skill: Resource, actor: str) -> None:
    from coffer.application.skill.follow_ops import audit_autobind_skipped

    for a in await service._rs.list(kind="agent"):
        if not a.enabled:
            continue
        # Non-folder delivery agents (rules_mdc — recognized extension point)
        # can't receive folder deliveries; skip auto-bind audibly rather than
        # raise per-agent. FOLDER and EXTERNAL_DIR agents both proceed.
        if not delivers_skill_folders(service, a):
            await audit_autobind_skipped(
                service=service,
                skill_name=skill.name,
                agent_name=a.name,
                reason="delivery_mode_unsupported",
                actor=actor,
            )
            continue
        # Per-agent follow policy (FR-025): agents that opted out of the
        # master library, or excluded this skill, are skipped — audibly, so
        # "imported but not delivered to agent X" is observable.
        follow, exclusions = service._resolve_agent_skill_policy(a)
        if not follow:
            await audit_autobind_skipped(
                service=service,
                skill_name=skill.name,
                agent_name=a.name,
                reason="not_following",
                actor=actor,
            )
            continue
        if skill.name in exclusions:
            await audit_autobind_skipped(
                service=service,
                skill_name=skill.name,
                agent_name=a.name,
                reason="excluded",
                actor=actor,
            )
            continue
        try:
            await service.enable_for(
                skill_name=skill.name, agent_name=a.name, force=False, actor=actor
            )
        except (CofferError, OSError) as e:
            # A per-agent failure (TargetConflict, config validation, OSError)
            # must not abort auto-bind for the rest — but it must not be silent
            # either: log + audit so the user can re-enable later.
            logger.warning("auto-bind of skill %r to agent %r skipped: %s", skill.name, a.name, e)
            await audit_autobind_skipped(
                service=service,
                skill_name=skill.name,
                agent_name=a.name,
                reason=str(e),
                actor=actor,
            )


async def relink_agent_skills(*, service: SkillService, agent_name: str, actor: str) -> None:
    """Re-deliver an agent's skills after its config_dir changed.

    Wired as the agent kind's on-config-dir-changed hook. The agent resource
    already carries the NEW config_dir when this runs, so the resolver gives
    the new ``<config_dir>/skills``. For each binding we remove the old link
    (``last_link_path``) and, if enabled, recreate it at the new location,
    repointing the binding row. Without this, changing an agent's config_dir
    orphaned the old links and left the new dir empty while verify reported
    no drift.

    ADR-045 hard grant (Task 11): a config_dir change must not resurrect a
    link that scope no longer grants. If the agent itself is out of scope on
    this machine, the whole run is a no-op — mirrors
    ``apply_follow_for_agent``'s early-out (its config dir may not even exist
    here). Per binding, a skill that has fallen out of (machine, agent) scope
    has its old link torn down like any other, but the new-location link is
    NOT recreated — the binding row is left untouched (not deleted); reclaim
    (disabling the row) is ``apply_follow_for_agent``'s job, not this hook's.
    No machine-id provider wired → no scope filtering at all (legacy
    relink-everything contract, same as the rest of the skill module).
    """
    try:
        agent = await service._rs.get(ResourceRef("agent", agent_name))
    except CofferError:
        return
    # Non-folder agents (rules_mdc — recognized extension point) have no folder
    # bindings to move; skip rather than crash on config-dir-change
    # reconciliation. FOLDER and EXTERNAL_DIR agents relink via their resolved
    # target dir.
    if not delivers_skill_folders(service, agent):
        return
    local = await service._local_machine_id()
    if local is not None and not machine_in_scope(agent.scope, local):
        # The agent itself isn't in scope on this machine — touch nothing.
        return
    new_skill_dir = service._resolve_agent_skill_dir(agent)
    skills_by_id = {s.id: s for s in await service._rs.list(kind="skill")}
    for b in await service._bindings.list_for_agent(agent.id):
        old_path = pathlib.Path(b.last_link_path) if b.last_link_path else None
        skill = skills_by_id.get(b.skill_resource_id)
        if skill is None:
            continue
        new_link = new_skill_dir / skill.name
        if old_path is not None and old_path == new_link:
            continue  # dir unchanged for this binding — nothing to move
        if old_path is not None:
            with contextlib.suppress(OSError):
                service._sync.remove_directory_link(old_path, link_mode=b.link_mode)
        if not b.enabled:
            continue
        if local is not None and not (
            machine_in_scope(skill.scope, local) and agent_in_scope(skill.scope, local, agent_name)
        ):
            # Out of scope at the new location — do not resurrect the link.
            # The row keeps its (now stale) enabled/last_link_path until a
            # follow run reclaims it; we only refuse to recreate here.
            continue
        master = service._store.paths_for(skill.name).folder
        try:
            new_skill_dir.mkdir(parents=True, exist_ok=True)
            if new_link.exists() or new_link.is_symlink():
                status = service._sync.classify_target(
                    link=new_link, expected_master=master, link_mode=b.link_mode
                )
                if status.drift is None:
                    # A correct Coffer link already sits at the new path (e.g. a
                    # prior partial run) — adopt it without re-linking, and
                    # record the binding so verify doesn't report a false
                    # MISSING_LINK against the now-removed old path.
                    mode = b.link_mode or infer_link_mode(new_link)
                else:
                    # FOREIGN content occupies the new path. Never clobber it,
                    # and never claim it as our link: recording a real link_mode
                    # (esp. COPY_FALLBACK) would let teardown rmtree the user's
                    # directory. link_mode=None makes teardown leave it intact
                    # and lets verify surface the genuine drift.
                    logger.warning(
                        "relink: foreign content at %s (skill %r / agent %r) — left intact",
                        new_link,
                        skill.name,
                        agent_name,
                    )
                    mode = None
            else:
                mode = service._sync.make_directory_link(target=master, link=new_link)
            await service._bindings.upsert(
                skill_id=b.skill_resource_id,
                agent_id=agent.id,
                enabled=True,
                last_linked_at=datetime.now(tz=UTC),
                last_link_path=str(new_link),
                link_mode=mode,
            )
            if mode is not None:
                with contextlib.suppress(Exception):
                    await service._audit.record(
                        AuditEventType.SKILL_RELINKED.value,
                        ref=ResourceRef("skill", skill.name),
                        actor=actor,
                        details={"agent": agent_name, "link": str(new_link)},
                    )
        except (CofferError, OSError) as e:
            logger.warning("relink of skill %r for agent %r skipped: %s", skill.name, agent_name, e)
            continue

    # EXTERNAL_DIR agents: the Coffer-owned external dir is agent-name-based, so
    # the links above don't move on a config-dir change — but the registration
    # target (the agent's config file) did, so re-apply it to the new config.
    await reconcile_external_registration(service, agent)
