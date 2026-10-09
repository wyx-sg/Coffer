"""Import helpers for SkillService.

Extracted to keep ``service.py`` under the file-size limit. Like
``binding_ops.py`` these are free functions that take the SkillService
instance and reach into its (private) attributes — they are conceptually
private to the skill subpackage.
"""

from __future__ import annotations

import logging
import pathlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from coffer.application.skill.builtin_seed import is_builtin
from coffer.domain.audit import AuditEventType
from coffer.domain.audit_diff import as_text, text_diff
from coffer.domain.errors import ResourceAlreadyExists, ResourceProtected
from coffer.domain.resource import Resource
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.source import ImportedSource
from coffer.domain.skill.validator import ValidationOk

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService

logger = logging.getLogger(__name__)


def _read_text(path: pathlib.Path) -> str | None:
    try:
        return as_text(path.read_bytes())
    except OSError:
        return None


def _skill_md_diff(service: SkillService, src: pathlib.Path, name: str) -> dict[str, object]:
    """The diff an overwrite makes to the master's SKILL.md (``{}`` when
    either side is unreadable or nothing changed)."""
    before = _read_text(service._store.paths_for(name).skill_md)
    after = _read_text(src / "SKILL.md")
    if before is None or after is None:
        return {}
    return text_diff(before, after, f"skills/{name}/SKILL.md")


def _refuse_overwriting_a_builtin(existing: list[Resource], name: str) -> None:
    """Refuse an import that would take over a skill Coffer generates.

    Deleting such a skill is already refused, but an overwriting import walked
    around that: it rewrote the row's ``source`` to ``local_import``, and a row
    that no longer looks builtin is no longer protected — the skill became
    deletable until the next boot seeded it back. The rule is deliberately
    "you may not overwrite a skill Coffer generates" rather than "this one name
    is magic", so it reads the same ``is_builtin`` predicate the delete guard
    and the read model do, and covers every generated skill there will ever be.
    """
    if any(r.name == name and is_builtin(r.config) for r in existing):
        raise ResourceProtected(
            f"skill {name}",
            "the name belongs to a skill Coffer generates and rewrites at every "
            "start; import under a different name",
        )


async def register_from_validated(
    *,
    service: SkillService,
    src: pathlib.Path,
    validation: ValidationOk,
    source_meta: ImportedSource,
    event: AuditEventType,
    actor: str,
    overwrite: bool = False,
    audit_details: dict[str, object] | None = None,
) -> Resource:
    name = validation.frontmatter.name
    # Duplicate check before copying any bytes. A skill's name is a label, but
    # it is still unique within the kind — and it is the master folder's name,
    # so the store is asked as well as the registry.
    existing = await service._rs.list(kind="skill")
    existing_row = next((r for r in existing if r.name == name), None)
    name_taken = existing_row is not None or service._store.exists(name)
    if name_taken and not overwrite:
        raise ResourceAlreadyExists("skill", name)
    _refuse_overwriting_a_builtin(existing, name)

    now = datetime.now(tz=UTC)
    cfg = SkillConfig(
        source=source_meta,
        # ``name`` is not stored on the config: it IS the resource's name,
        # taken from the frontmatter right here. See ``SkillConfig``.
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

    changed: dict[str, object] = {}
    if name_taken:
        # What an overwrite changes, read before the swap: the version it
        # replaces and SKILL.md's diff (the skill's own text, never config).
        changed["overwrite"] = True
        if existing_row is not None:
            changed["previous_version_hash"] = existing_row.config.get("version_hash")
        changed.update(_skill_md_diff(service, src, name))
        # Overwrite path: swap the master folder in place (atomic_replace also
        # covers an orphan master folder with no row — DriftKind.ORPHAN_MASTER).
        service._store.atomic_replace(src=src, name=name, meta=meta)
        if existing_row is not None:
            # Update the existing row, preserving its uid + id + per-agent
            # bindings + delivered symlinks (the master folder path is
            # unchanged). Re-importing a skill is an update of the same
            # resource, so its identity must survive it.
            r = await service._rs.update_config(
                existing_row.uid,
                new_config=cfg.model_dump(mode="json"),
                actor=actor,
                description=validation.frontmatter.description,
                allow_lifecycle_kind=True,  # creation seam: master folder replaced above
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
                allow_lifecycle_kind=True,  # creation seam: master folder replaced above
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
                allow_lifecycle_kind=True,  # creation seam: master folder created above
            )
        except Exception:
            # Best-effort rollback of master
            service._store.delete(name)
            raise
        audit_event = event

    await service._audit.record(
        audit_event.value,
        resource=r,
        actor=actor,
        details={
            "version_hash": validation.skill_md_sha256,
            "source_type": source_meta.type,
            **changed,
            **(audit_details or {}),
        },
    )
    # Deliver to every agent the skill's own state grants (spec skill-manager
    # "Deliver a skill only where it is enabled and in scope"). An overwrite
    # changes neither half of that rule, so its pass finds nothing to do.
    await service.reconcile_delivery()
    return r
