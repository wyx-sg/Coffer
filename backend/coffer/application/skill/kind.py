"""`skill` Kind wiring used by the composition root.

The `on_delete` hook tears down per-agent symlinks before the resource row
is deleted. It is exposed as an *async* callable so ResourceService can
``await`` it: a previous fire-and-forget implementation scheduled the
cleanup with ``loop.create_task`` and let ``_rs.delete`` proceed in
parallel — by the time the background coroutine called ``_rs.get(ref)``
the row was gone and the cleanup raised ResourceNotFound (silently
suppressed), orphaning every symlink and the master folder.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from coffer.application.skill.builtin_seed import is_builtin
from coffer.domain.errors import ResourceProtected
from coffer.domain.resource import Kind, Resource, ResourceRef
from coffer.domain.skill.config import SkillConfig

AsyncOnDelete = Callable[[ResourceRef], Awaitable[None]]
# Sync or async — ResourceService awaits the result if it's an Awaitable.
OnScopeChangedHook = Callable[[ResourceRef], Awaitable[None] | None]
OnEnabledChangedHook = Callable[[ResourceRef], Awaitable[None] | None]


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
            str(skill.ref),
            "it is rewritten from the running build at every start, so "
            "deleting it would not last; disable it instead, or narrow its scope",
        )


def _row_converges(config: dict[str, object]) -> bool:
    """Whether one skill row travels to the user's other machines.

    Every skill a person imported does. Coffer's own does not: its master
    folder is rendered locally from the running build, the knowledge files
    (which converge on their own) and **this machine's own switches** — which
    collections are enabled is machine-local reach (spec vault-sync FR-014) and
    deliberately stays home.

    So two machines holding identical knowledge but a different set of
    collections switched on render different bytes, each correct where it is.
    Publishing either — the folder or the row whose ``version_hash`` is that
    folder's digest — makes the other overwrite it, and the overwritten machine
    re-renders on its next boot or curation tick and publishes back. That is a
    commit and an audit event per tick on both machines, forever, over an
    artifact neither machine reads from the other. The same is true of any
    version skew, since the shipped half of the text moves between builds.

    It is derived output, so it is regenerated rather than received: every
    machine already has everything it takes to produce its own.
    """
    return not is_builtin(config)


def make_skill_kind(
    cleanup_bindings_for_skill: AsyncOnDelete,
    on_scope_changed: OnScopeChangedHook | None = None,
    on_enabled_changed: OnEnabledChangedHook | None = None,
) -> Kind:
    async def _on_delete(ref: ResourceRef) -> None:
        # Awaited by ResourceService.delete BEFORE the row is removed, so
        # ``cleanup_bindings_for_skill`` can still resolve the resource
        # via ``_rs.get(ref)`` and tear down every symlink + binding row
        # before the kind-agnostic cascade kicks in.
        await cleanup_bindings_for_skill(ref)

    return Kind(
        name="skill",
        display_name="Skill",
        config_schema=SkillConfig,
        on_delete=_on_delete,
        # A builtin skill's row is Coffer's, not the user's: deleting it is a
        # no-op the next boot undoes, so the framework refuses it up front
        # for every surface at once.
        validate_delete=_refuse_builtin_delete,
        # ...and for the same reason its row does not travel, while every
        # other skill's does. ``converges`` stays True for the kind; this
        # withholds the one row that is derived output (spec vault-sync
        # FR-093).
        converges_row=_row_converges,
        # A skill row must be backed by an imported master folder under
        # ~/.coffer/skills/. Only SkillService (which creates that folder) may
        # register it; the generic POST /resources path is rejected (CODE-REG).
        generic_create_allowed=False,
        # ADR per-agent-resource-scope: scope is one half of the whole delivery rule —
        # ``enabled AND scope.is_active(scope, agent)``.
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
