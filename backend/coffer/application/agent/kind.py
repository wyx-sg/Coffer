"""`agent` Kind wiring used by the composition root.

The `on_delete` hook is composed at the composition root rather than baked
in here, because removing an agent may need to cascade into the *skill*
module — and per Contract 5, this module must not import any skill code.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.resource import Kind, Resource
from coffer.domain.vault.layout import StorageClass

# Sync or async — ResourceService awaits the result if it's an Awaitable.
# Both hooks are handed the agent ROW rather than an identifier to look it up
# with: the caller performing the mutation already has it, and a hook that
# needs the identity reads ``resource.uid``.
OnDeleteHook = Callable[[Resource], Awaitable[None] | None]


def agent_name_for(config: dict[str, Any]) -> str:
    """The one name an agent row may carry: its type's (spec agent-registry
    "Keep one agent per type, named by it"). ``claude_code`` → ``claude-code``."""
    return AgentType(config["type"]).default_name()


def make_agent_kind(on_delete: OnDeleteHook | None = None) -> Kind:
    """Construct the `agent` Kind.

    `on_delete` (if provided) is invoked by ResourceService BEFORE the
    persistence delete; raising aborts the deletion. Async hooks are
    awaited (so symlink + binding-row cleanup completes before the agent
    row vanishes); sync hooks run inline. The skill module supplies the
    callback at the composition root.

    An agent is not toggleable: it is connected or disconnected, never switched
    off, so there is no ``on_enabled_changed`` hook.

    The kind declares no activation scope (ADR per-agent-resource-scope): scope names the agents a
    resource is active for, so an agent scoping itself is meaningless. A
    non-null scope is rejected at validation (422).
    """
    return Kind(
        name="agent",
        display_name="Agent",
        config_schema=AgentConfig,
        on_delete=on_delete,
        toggleable=False,
        # An agent row is created from detection/validation of an on-disk config
        # dir by AgentService; the generic POST /resources path must not create
        # an undetected, folder-less agent (spec resource-framework "Keep
        # creation a per-kind seam").
        generic_create_allowed=False,
        # One agent per type, named by it: the name is derived from the type,
        # so it is fixed and nothing else — no title, no description — is a
        # person's to choose (spec agent-registry "Keep one agent per type,
        # named by it").
        name_from_config=agent_name_for,
        name_fixed=True,
        titled=False,
        # An agent names a config directory on THIS disk: it is true of this
        # machine only, so it is filed under ``local/`` and never travels
        # (ADR storage-is-five-classes-by-nature).
        storage=StorageClass.LOCAL,
    )
