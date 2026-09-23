"""The SKILL.md half of a skill rename.

A skill's resource name is *derived* from its SKILL.md frontmatter at import
(``lifecycle_ops`` reads ``validation.frontmatter.name`` and makes it the row's
name), and the agent product reads that same field to decide what the skill is
called. So the frontmatter is not a copy of the name that happens to go stale —
it is where the name came from, and the thing the user is actually renaming as
far as their agent is concerned. A rename the agent never sees is not a rename.

Split from ``rename_ops`` for the file-size limit, and along a real seam: that
module moves a FOLDER and the links pointing at it, this one edits a FILE and
the one config field describing it.

Why the hash is recomputed
--------------------------
Rewriting SKILL.md changes its bytes, and ``config.version_hash`` is defined as
the sha256 of the SKILL.md currently in master — it is what a re-import
compares against and what the UI and ``coffer skill show`` print. Leaving it
would make that field a hash of bytes that no longer exist anywhere.

Note that drift detection is NOT the reason: ``sync_engine.classify_target``
compares the link against the master PATH and never hashes content, so a stale
hash would not have produced a false drift report today. It would simply have
been wrong, and wrong in the one field whose entire job is to say whether the
content changed.

What this deliberately does not touch
-------------------------------------
``.coffer.meta.json``, which also records the name Coffer imported the folder
under. It has no reader anywhere — not in Coffer, not in any agent product —
so rewriting it would be bookkeeping for an audience of nobody. The SKILL.md
rewrite is different precisely because it HAS a reader.

Rollback
--------
Each step here undoes the writes before it — including the folder move
``rename_ops`` made — so a failure raises with the vault exactly as it was and
the pre-write hook aborts the rename cleanly. ``rename_ops``' header documents
the one residual window, where the undo itself fails.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.domain.errors import SkillValidationError
from coffer.domain.resource import Resource
from coffer.domain.skill.frontmatter import rewrite_name

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillMdRewrite:
    """The SKILL.md edit a rename implies, computed before anything moves."""

    original: bytes
    rewritten: bytes
    new_hash: str


def plan_skill_md_rewrite(
    service: SkillService, old_name: str, new_name: str
) -> SkillMdRewrite | None:
    """Read the master's SKILL.md and compute the bytes the rename wants there.

    Returns ``None`` when there is no master SKILL.md to rewrite — the same
    already-broken vault the folder move tolerates, where there is no file to
    make consistent and no content to hash.

    Raises ``SkillValidationError`` when the file IS there but carries no
    frontmatter ``name`` to replace. That is a master a user has hand-edited
    into a shape Coffer's own importer would reject, and a rename cannot make
    it consistent — so it refuses, before anything moves, rather than quietly
    leaving the file naming the old skill.
    """
    skill_md = service._store.paths_for(old_name).skill_md
    if not skill_md.is_file():
        return None
    original = skill_md.read_bytes()
    # ``errors="replace"`` matches the validator, so a file with a bad byte
    # fails the same way here as it would on import rather than raising
    # UnicodeDecodeError out of a rename.
    rewritten_text = rewrite_name(original.decode("utf-8", errors="replace"), new_name)
    if rewritten_text is None:
        raise SkillValidationError(
            "skill_md_frontmatter_name_missing",
            {"path": str(skill_md), "new_name": new_name},
        )
    rewritten = rewritten_text.encode("utf-8")
    return SkillMdRewrite(
        original=original,
        rewritten=rewritten,
        new_hash=hashlib.sha256(rewritten).hexdigest(),
    )


async def apply_skill_md_rewrite(
    *,
    service: SkillService,
    skill: Resource,
    new_name: str,
    rewrite: SkillMdRewrite,
) -> None:
    """Write the rewritten SKILL.md and bring ``version_hash`` back in step.

    Each failure undoes the writes that came before it, so the caller's
    ``raise`` really does mean "nothing moved" (see this module's header).
    """
    skill_md = service._store.paths_for(new_name).skill_md
    try:
        skill_md.write_bytes(rewrite.rewritten)
    except OSError:
        _undo_folder_move(service, moved_to=new_name, back_to=skill.name)
        raise

    # ``version_hash`` describes the file that was just rewritten, so it moves
    # with it — and it is the ONLY config field a rename touches, because the
    # name itself is not duplicated onto the config any more (see
    # ``SkillConfig``). Written through the service rather than the repo: this
    # is the skill kind editing its own config, the same path a re-import takes
    # (``lifecycle_ops``), and ``allow_lifecycle_kind`` is how a kind that owns
    # an on-disk artifact opts past the per-kind creation guard. ``description`` is
    # passed explicitly because the repo overwrites that column
    # unconditionally — omitting it would erase the skill's description as a
    # side effect of a rename.
    config = dict(skill.config)
    config["version_hash"] = rewrite.new_hash
    try:
        await service._rs.update_config(
            skill.uid,
            new_config=config,
            actor="system",
            description=skill.description,
            allow_lifecycle_kind=True,
        )
    except Exception:
        with contextlib.suppress(OSError):
            skill_md.write_bytes(rewrite.original)
        _undo_folder_move(service, moved_to=new_name, back_to=skill.name)
        raise


def _undo_folder_move(service: SkillService, *, moved_to: str, back_to: str) -> None:
    """Put the master folder back under ``back_to`` after a failed rename step.

    Best-effort by necessity — it is itself a filesystem call, made moments
    after one that just failed. If it fails too, the folder is left under a
    name no row claims while the row keeps a name no folder answers to, which
    ``verify`` reports as MISSING_MASTER plus ORPHAN_MASTER. Nothing repairs
    that automatically, which is why it is the one thing this module logs at
    ERROR.
    """
    try:
        service._store.rename(old_name=moved_to, new_name=back_to)
    except OSError:
        logger.error(
            "rename of skill %r aborted, but the master folder could not be moved "
            "back from %r — the folder and the resource row now disagree and need "
            "to be reconciled by hand",
            back_to,
            moved_to,
            exc_info=True,
        )
