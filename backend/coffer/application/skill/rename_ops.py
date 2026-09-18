"""The skill kind's ``on_rename`` hook: carry the folders with the label.

Extracted to keep ``service.py`` under the file-size limit, beside
``binding_ops`` / ``delivery_ops`` / ``lifecycle_ops``: free functions that
take the SkillService instance and reach into its (private) attributes,
conceptually private to the skill subpackage.

A skill's name is a label (ADR resource-identity-is-an-immutable-uid) — the
identity is the uid, and every binding row addresses the skill by its integer
``resources.id``, so a rename touches no reference anywhere in the database.
What it does touch is three copies of the NAME that live outside that row:

1. the canonical master folder ``~/.coffer/skills/<name>``,
2. the copy delivered into each agent's skills dir as ``<skill_dir>/<name>``,
   a symlink (or junction, or copied tree) pointing at (1), and
3. the ``name:`` in that master folder's own ``SKILL.md`` frontmatter.

None of the three is a reference Coffer could have held by uid instead. (1) is
the folder the user opens in their own editor and (2) is how the agent product
discovers a skill — both read the DIRECTORY NAME. (3) is the agent product's
own idea of what the skill is CALLED: it is a field in a file format Coffer
does not own, and a rename the agent never sees is not a rename. The resource's
name is in fact *derived* from (3) at import (``lifecycle_ops``), so leaving it
behind would not merely look untidy — it would leave the row and the file
disagreeing about which of them the name came from.

Carrying (3) is also why the kind declares ``validate_name``: the frontmatter's
charset is narrower than the framework's, so without it a perfectly legal
``PATCH {"name": "My.Skill"}`` would write a SKILL.md that Coffer's own
importer rejects. See ``domain/skill/frontmatter.validate_frontmatter_name``.
The edit to (3) itself lives in ``rename_skill_md.py``, which explains what it
rewrites, what it leaves alone, and why the hash moves with it.

Order of operations, and what a half-finished rename leaves behind
-----------------------------------------------------------------
Everything that can be decided without touching anything is decided first: the
rewritten SKILL.md bytes and their hash are computed from the OLD folder, so a
master whose frontmatter cannot carry the new name aborts the rename before a
single byte moves.

Then the three writes, in an order chosen so that each one can be undone by the
one before it:

1. ``MasterStore.rename`` — a single same-directory ``os.rename``, atomic on
   POSIX and NTFS, so the skill is never visible under both names or neither.
2. the rewritten ``SKILL.md``; on failure the folder is moved back.
3. ``config.version_hash``, which describes those bytes; on failure the
   original SKILL.md bytes are restored and the folder is moved back.

So a failure anywhere in 1-3 raises with the vault exactly as it was, which is
what the hook running PRE-write is for: the row never takes the new name.

The residual window is the undo itself. If the rollback rename in 2 or 3 also
fails — a second filesystem error moments after the first — the master folder
is left under the NEW name while the row keeps the OLD one, and every delivery
dangles. Nothing repairs that automatically: ``verify`` will report
MISSING_MASTER for the skill and ORPHAN_MASTER for the folder now sitting
unclaimed beside it, which together name both halves of what a person has to
put back by hand. The failed rollback is logged at ERROR, because it is the
only state this module can produce that a human has to resolve.

The delivered links move LAST and are best-effort per agent. They deliberately
cannot raise: by then the row is about to take the new name, and aborting would
leave the name disagreeing with the folder it names — worse than a stale
symlink, and unrepairable. A stale symlink is exactly the drift
``SkillService.verify`` reports and ``repair_drift`` fixes, and the drift boot
heal runs that repair at every daemon start (``application/skill/boot_reconcile``).
So a half-finished link pass degrades to "this agent loses the skill until the
next boot", never to "Coffer has forgotten where the skill is".

Reversibility
-------------
``resource_rename_ops`` calls this hook a second time, with the arguments
swapped, when a racing writer claims the new name between the collision check
and the commit. That works because every step is a function of
``(resource.name -> new_name)``: handed the resource as it now stands and the
name to put it back under, the hook undoes itself — folder, file, config and
links alike. The cost is that the config write happens through
``ResourceService.update_config``, so such a rollback leaves two
``resource_updated`` rows in the audit trail describing a round trip. That is
an honest record of what happened, and the alternative — a config write that
bypasses the service — is the kind of reaching-around this layering exists to
prevent.
"""

from __future__ import annotations

import contextlib
import logging
import pathlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from coffer.application.skill.lifecycle_ops import infer_link_mode
from coffer.application.skill.rename_skill_md import (
    apply_skill_md_rewrite,
    plan_skill_md_rewrite,
)
from coffer.domain.error_base import CofferError
from coffer.domain.resource import Resource
from coffer.domain.skill.binding import LinkMode

if TYPE_CHECKING:
    from coffer.application.skill.service import SkillService

logger = logging.getLogger(__name__)


async def move_master_folder(
    *,
    service: SkillService,
    skill: Resource,
    new_name: str,
) -> None:
    """Carry a skill's folder, its SKILL.md and its delivered copies to ``new_name``."""
    old_name = skill.name
    if new_name == old_name:
        # Defensive: ResourceService.rename already short-circuits a no-op
        # rename. Re-checked here because a no-op ``os.rename`` onto an
        # existing destination is exactly what the store refuses.
        return

    # Decided before anything moves, so a master whose frontmatter cannot carry
    # the new name aborts the rename rather than half-applying it.
    rewrite = plan_skill_md_rewrite(service, old_name, new_name)

    try:
        service._store.rename(old_name=old_name, new_name=new_name)
    except FileNotFoundError:
        # The master folder is already gone — verify() would be calling this
        # skill MISSING_MASTER. Refusing the rename here would make a label the
        # user can never correct on a vault that is ALREADY broken, and moving
        # nothing is a faithful description of what is on disk. The row still
        # renames; the drift it had before is the drift it has after.
        logger.warning(
            "rename of skill %r to %r: no master folder to move (already missing)",
            old_name,
            new_name,
        )
    # Anything else — most importantly FileExistsError, something already
    # occupying the destination — propagates and aborts the rename. Nothing has
    # moved at that point.

    if rewrite is not None:
        await apply_skill_md_rewrite(
            service=service,
            skill=skill,
            new_name=new_name,
            rewrite=rewrite,
        )

    await _move_delivered_links(service=service, skill=skill, new_name=new_name)


async def _move_delivered_links(
    *,
    service: SkillService,
    skill: Resource,
    new_name: str,
) -> None:
    """Re-point every live delivery of ``skill`` at ``<skill_dir>/<new_name>``.

    Binding rows are addressed by ``resources.id`` and are NOT touched by the
    rename — the same rows come back afterwards, which is the point of the
    integer join key. Only their recorded ``last_link_path`` moves.
    """
    master = service._store.paths_for(new_name).folder
    agents_by_id = {a.id: a for a in await service._rs.list(kind="agent")}

    for binding in await service._bindings.list_for_skill(skill.id):
        if not binding.enabled:
            # A spent row: the copy was already reclaimed, so there is nothing
            # on disk under either name. Leaving it alone keeps the bookkeeping
            # honest — it records a delivery that ended, not one to move.
            continue
        agent = agents_by_id.get(binding.agent_resource_id)
        if agent is None:
            continue
        old_link = pathlib.Path(binding.last_link_path) if binding.last_link_path else None
        new_link = service._resolve_agent_skill_dir(agent) / new_name
        try:
            await _move_one_link(
                service=service,
                skill_id=skill.id,
                agent_id=agent.id,
                old_link=old_link,
                new_link=new_link,
                master=master,
                recorded_mode=binding.link_mode,
            )
        except (CofferError, OSError) as e:
            # The link for this agent stays where it was, now dangling: the
            # master it pointed at has moved. The binding row keeps the stale
            # path, so verify() reports MISSING_LINK and repair_drift re-links
            # from the CURRENT name — the boot heal runs that unattended. One
            # agent's failure must not stop the rest from following the rename.
            logger.warning(
                "rename of skill %r to %r: could not move the copy delivered to agent %r: %s",
                skill.name,
                new_name,
                agent.name,
                e,
            )


async def _move_one_link(
    *,
    service: SkillService,
    skill_id: int,
    agent_id: int,
    old_link: pathlib.Path | None,
    new_link: pathlib.Path,
    master: pathlib.Path,
    recorded_mode: LinkMode | None,
) -> None:
    mode = recorded_mode
    if old_link is not None and old_link != new_link:
        # Removed rather than left in place: the master it names has already
        # moved, so what remains is a broken link inside the user's own agent
        # directory. ``remove_directory_link`` is told the recorded mode so a
        # copy-fallback tree is removed as a tree and a symlink as a symlink.
        with contextlib.suppress(OSError):
            service._sync.remove_directory_link(old_link, link_mode=mode)

    new_link.parent.mkdir(parents=True, exist_ok=True)
    if new_link.exists() or new_link.is_symlink():
        status = service._sync.classify_target(
            link=new_link,
            expected_master=master,
            link_mode=mode,
        )
        if status.drift is not None:
            # Something that is not ours already sits where the renamed skill
            # would be delivered — an unmanaged skill folder of the same name,
            # most likely. Coffer never clobbers foreign content, so the
            # delivery is dropped and the row is told it holds no link. The row
            # stays ENABLED on purpose: verify() then falls back to
            # ``<skill_dir>/<current name>``, names that exact path, and
            # reports the real REPLACED_WITH_REGULAR, which repair_drift
            # deliberately refuses to fix by itself.
            logger.warning(
                "rename: foreign content at %s — the delivered copy was not moved there",
                new_link,
            )
            await service._bindings.upsert(
                skill_id=skill_id,
                agent_id=agent_id,
                enabled=True,
                last_link_path=None,
                link_mode=None,
            )
            return
        # A correct link is already there (a retried rename, or the agent's
        # skill dir and the new name happening to coincide with it). Adopt it.
        new_mode = mode or infer_link_mode(new_link)
    else:
        new_mode = service._sync.make_directory_link(target=master, link=new_link)

    await service._bindings.upsert(
        skill_id=skill_id,
        agent_id=agent_id,
        enabled=True,
        last_linked_at=datetime.now(tz=UTC),
        last_link_path=str(new_link),
        link_mode=new_mode,
    )
