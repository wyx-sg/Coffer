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


def make_skill_kind(cleanup_bindings_for_skill: AsyncOnDelete) -> Kind:
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
    )
