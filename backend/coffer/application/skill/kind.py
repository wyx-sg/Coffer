"""`skill` Kind wiring used by the composition root.

Every hook here is handed the ``Resource`` it concerns rather than an
identifier to look it up with. A hook that needs the identity reads
``resource.uid``; one that needs the label reads ``resource.name``. That is
what replaced the old ``ResourceRef``, and it removes a lookup that could fail
in the one place it must not: the resource performing the mutation is already
in the caller's hand.

The `on_delete` hook tears down per-agent symlinks before the resource row
is deleted. It is exposed as an *async* callable so ResourceService can
``await`` it: a previous fire-and-forget implementation scheduled the
cleanup with ``loop.create_task`` and let ``_rs.delete`` proceed in
parallel — by the time the background coroutine looked the resource up again
the row was gone and the cleanup raised ResourceNotFound (silently
suppressed), orphaning every symlink and the master folder.

The `on_rename` hook is what a rename costs this kind. A skill's name is also
a directory — ``~/.coffer/skills/<name>`` — and the copies delivered into each
agent's skills dir are named after it too, so the label cannot move on its own.
It is PRE-write: raising aborts the rename with nothing moved, which is the
only ordering under which a failure leaves the row and the disk agreeing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from coffer.domain.resource import Kind, Resource
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.frontmatter import validate_frontmatter_name

AsyncOnDelete = Callable[[Resource], Awaitable[None]]
# Sync or async — ResourceService awaits the result if it's an Awaitable.
OnScopeChangedHook = Callable[[Resource], Awaitable[None] | None]
OnEnabledChangedHook = Callable[[Resource], Awaitable[None] | None]
#: ``(skill_as_it_stands, new_name)``. Awaited by ResourceService.rename
#: BEFORE the row moves.
AsyncOnRename = Callable[[Resource, str], Awaitable[None]]


def make_skill_kind(
    cleanup_bindings_for_skill: AsyncOnDelete,
    move_master_folder: AsyncOnRename,
    on_scope_changed: OnScopeChangedHook | None = None,
    on_enabled_changed: OnEnabledChangedHook | None = None,
) -> Kind:
    async def _on_delete(skill: Resource) -> None:
        # Awaited by ResourceService.delete BEFORE the row is removed, so
        # ``cleanup_bindings_for_skill`` can still read the binding rows that
        # ``ON DELETE CASCADE`` is about to take with it, and tear down every
        # symlink + the master folder first.
        await cleanup_bindings_for_skill(skill)

    async def _on_rename(skill: Resource, new_name: str) -> None:
        # Awaited by ResourceService.rename BEFORE the row's name column
        # changes. ``move_master_folder`` raises if the master folder cannot
        # move, and the rename is abandoned with the row and the disk both
        # still on the old name.
        await move_master_folder(skill, new_name)

    return Kind(
        name="skill",
        display_name="Skill",
        config_schema=SkillConfig,
        # The framework's name rule is a superset of the frontmatter's, and a
        # skill's name is not only a directory: it is written into the
        # SKILL.md that the agent product reads. Declaring the kind's own,
        # narrower rule is what stops a rename producing a file Coffer's own
        # importer would then reject. The framework runs this on register AND
        # rename, so the two cannot drift.
        validate_name=validate_frontmatter_name,
        on_delete=_on_delete,
        # A skill's name is a directory under ~/.coffer/skills/ and the name of
        # every copy delivered into an agent's skills dir, so renaming the row
        # alone would leave the label pointing at nothing.
        on_rename=_on_rename,
        # A skill row must be backed by an imported master folder under
        # ~/.coffer/skills/. Only SkillService (which creates that folder) may
        # register it; the generic POST /resources path is rejected (CODE-REG).
        generic_create_allowed=False,
        # ADR per-agent-resource-scope: scope is one half of the whole delivery rule —
        # ``enabled AND scope.is_active(scope, agent_uid)``.
        supports_scope=True,
        # A skill's scope edit re-runs delivery reconciliation for every agent
        # (the composition root supplies the callback — the same
        # reconciliation the sync post-import hook uses,
        # ``apply_scope_for_agent``, per registered agent).
        on_scope_changed=on_scope_changed,
        # The other half: a skill's ``enabled`` flag is a real delivery switch,
        # so disabling reclaims every delivered copy and re-enabling
        # redelivers. Same callback, same per-agent reconciliation.
        on_enabled_changed=on_enabled_changed,
    )
