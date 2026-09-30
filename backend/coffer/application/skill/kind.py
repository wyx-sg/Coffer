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

A skill's name is fixed (``name_fixed``). It is the directory an agent loads
the skill from and the ``name:`` its SKILL.md declares, so agents, other skills
and the user's own notes quote it; a rename would break every one of them
(ADR names-visible-to-agents-are-fixed). The framework refuses a changed name
before anything moves, so this kind supplies no rename hook. It carries no
title either (``titled=False``): a skill is its fixed name and its SKILL.md
description.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from coffer.application.skill.builtin_seed import is_builtin
from coffer.domain.errors import ResourceProtected
from coffer.domain.resource import Kind, Resource
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.frontmatter import validate_frontmatter_name
from coffer.domain.vault.layout import StorageClass

AsyncOnDelete = Callable[[Resource], Awaitable[None]]
# Sync or async — ResourceService awaits the result if it's an Awaitable.
OnScopeChangedHook = Callable[[Resource], Awaitable[None] | None]
OnEnabledChangedHook = Callable[[Resource], Awaitable[None] | None]


def _refuse_builtin_delete(skill: Resource) -> None:
    """Refuse to delete a skill Coffer generates.

    The master folder is rewritten from the running build at the next boot, so
    the delete would undo itself — a destructive-looking operation that leaves
    the vault exactly where it started, minus whatever links it tore down on
    the way. ``enabled`` and ``scope`` stay available: those decide reach,
    which is the owner's call; existence is not.
    """
    if is_builtin(skill.config):
        raise ResourceProtected(
            # The LABEL, not the uid: this message is read by whoever asked
            # for the delete, and they asked for it by name. The import half
            # of the same refusal, over in ``lifecycle_ops``, phrases its
            # subject exactly this way, so the two read as one rule.
            f"skill {skill.name}",
            "it is rewritten from the running build at every start, so "
            "deleting it would not last; disable it instead, or narrow its scope",
        )


def _row_storage(config: dict[str, object]) -> StorageClass:
    """Where one skill row is filed (ADR storage-is-five-classes-by-nature).

    Every skill a person imported is in the vault. Coffer's own is not: its
    master folder is rendered locally from the running build, the knowledge
    files and **this machine's own inputs** — its experimental-feature
    switches, which decide which sections of the manual render — so two
    machines holding identical knowledge render different bytes, each correct
    where it is. It is derived output, so it is filed under ``derived/`` and
    regenerated rather than received: every machine already has everything it
    takes to produce its own.
    """
    return StorageClass.DERIVED if is_builtin(config) else StorageClass.VAULT


def make_skill_kind(
    cleanup_bindings_for_skill: AsyncOnDelete,
    on_scope_changed: OnScopeChangedHook | None = None,
    on_enabled_changed: OnEnabledChangedHook | None = None,
) -> Kind:
    async def _on_delete(skill: Resource) -> None:
        # Awaited by ResourceService.delete BEFORE the file is removed, so
        # ``cleanup_bindings_for_skill`` can still resolve the skill, drop its
        # binding rows and tear down every symlink + the master folder first.
        await cleanup_bindings_for_skill(skill)

    return Kind(
        name="skill",
        display_name="Skill",
        config_schema=SkillConfig,
        # The framework's name rule is a superset of the frontmatter's, and a
        # skill's name is not only a directory: it is written into the
        # SKILL.md that the agent product reads. Declaring the kind's own,
        # narrower rule is what stops registration accepting a name Coffer's
        # own importer would then reject.
        validate_name=validate_frontmatter_name,
        on_delete=_on_delete,
        # A skill's name is its master folder under ~/.coffer/vault/skills/, the name
        # of every copy delivered into an agent's skills dir and the SKILL.md
        # ``name:`` — all quoted by agents — so it never changes. A new name
        # means removing the skill and importing it again.
        name_fixed=True,
        name_fixed_resets="its enabled flag, its scope and its deliveries to agents",
        titled=False,
        # A builtin skill's row is Coffer's, not the user's: deleting it is a
        # no-op the next boot undoes, so the framework refuses it up front
        # for every surface at once.
        validate_delete=_refuse_builtin_delete,
        # ...and for the same reason its row is derived output, filed under
        # ``derived/`` while every other skill's is in the vault.
        storage_row=_row_storage,
        # A skill row must be backed by an imported master folder under
        # ~/.coffer/vault/skills/. Only SkillService (which creates that folder) may
        # register it; the generic POST /resources path is rejected (spec
        # resource-framework "Keep creation a per-kind seam").
        generic_create_allowed=False,
        # ADR per-agent-resource-scope: scope is one half of the whole delivery rule —
        # ``enabled AND scope.is_active(scope, agent_uid)``.
        supports_scope=True,
        # A skill's scope edit asks for a ``skill_link`` reconcile pass (the
        # composition root supplies the callback), which delivers to and
        # reclaims from every agent at once.
        on_scope_changed=on_scope_changed,
        # The other half: a skill's ``enabled`` flag is a real delivery switch,
        # so disabling reclaims every delivered copy and re-enabling
        # redelivers. Same callback, same pass.
        on_enabled_changed=on_enabled_changed,
    )
