"""`agent` Kind wiring used by the composition root.

The `on_delete` hook is composed at the composition root rather than baked
in here, because removing an agent may need to cascade into the *skill*
module — and per Contract 5, this module must not import any skill code.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from coffer.domain.agent.config import AgentConfig
from coffer.domain.resource import Kind, ResourceRef

# Sync or async — ResourceService awaits the result if it's an Awaitable.
OnDeleteHook = Callable[[ResourceRef], Awaitable[None] | None]
OnScopeChangedHook = Callable[[ResourceRef], Awaitable[None] | None]


def make_agent_kind(
    on_delete: OnDeleteHook | None = None,
    on_scope_changed: OnScopeChangedHook | None = None,
) -> Kind:
    """Construct the `agent` Kind.

    `on_delete` (if provided) is invoked by ResourceService BEFORE the
    persistence delete; raising aborts the deletion. Async hooks are
    awaited (so symlink + binding-row cleanup completes before the agent
    row vanishes); sync hooks run inline. The skill module supplies the
    callback at the composition root.

    `on_scope_changed` (if provided) is invoked by ResourceService.update_scope
    AFTER persistence + audit (ADR-045 / Task 11 Fix 2): re-runs the agent's
    own follow reconciliation so a scope edit is applied immediately instead
    of waiting on an unrelated trigger.
    """
    return Kind(
        name="agent",
        display_name="Agent",
        config_schema=AgentConfig,
        on_delete=on_delete,
        # An agent row is created from detection/validation of an on-disk config
        # dir by AgentService; the generic POST /resources path must not create
        # an undetected, folder-less agent (CODE-REG).
        generic_create_allowed=False,
        scope_axes=("machine",),
        on_scope_changed=on_scope_changed,
    )
