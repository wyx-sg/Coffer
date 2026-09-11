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

from coffer.domain.resource import Kind, ResourceRef
from coffer.domain.skill.config import SkillConfig

AsyncOnDelete = Callable[[ResourceRef], Awaitable[None]]
# Sync or async — ResourceService awaits the result if it's an Awaitable.
OnScopeChangedHook = Callable[[ResourceRef], Awaitable[None] | None]
OnEnabledChangedHook = Callable[[ResourceRef], Awaitable[None] | None]


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
        # A skill row must be backed by an imported master folder under
        # ~/.coffer/skills/. Only SkillService (which creates that folder) may
        # register it; the generic POST /resources path is rejected (CODE-REG).
        generic_create_allowed=False,
        # ADR per-agent-resource-scope: scope is one half of the whole delivery rule —
        # ``enabled AND agent_in_scope(scope, agent)``.
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
