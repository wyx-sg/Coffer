"""`agent` Kind wiring used by the composition root.

The `on_delete` hook is composed at the composition root rather than baked
in here, because removing an agent may need to cascade into the *skill*
module — and per Contract 5, this module must not import any skill code.
"""

from __future__ import annotations

from collections.abc import Callable

from coffer.domain.agent.config import AgentConfig
from coffer.domain.resource import Kind, ResourceRef

OnDeleteHook = Callable[[ResourceRef], None]


def make_agent_kind(on_delete: OnDeleteHook | None = None) -> Kind:
    """Construct the `agent` Kind.

    `on_delete` (if provided) is invoked synchronously by ResourceService
    BEFORE the persistence delete; raising aborts the deletion. It is the
    place where skill bindings are cleaned up (the skill module supplies
    the callback at the composition root).
    """
    return Kind(
        name="agent",
        display_name="Agent",
        config_schema=AgentConfig,
        on_delete=on_delete,
    )
