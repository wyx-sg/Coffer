"""`builtin_agent` Kind wiring + default seeding.

Mirrors the `agent` kind pattern: the Kind descriptor is built here and the
optional ``on_delete`` guard (refuse to remove the last built-in agent) is
composed at the composition root, which can reference the ResourceService to
count the survivors.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.builtin_agent.config import BuiltinAgentConfig
from coffer.domain.resource import Kind, Resource, ResourceRef

BUILTIN_AGENT_KIND = "builtin_agent"

# Name of the auto-seeded default built-in agent.
DEFAULT_BUILTIN_NAME = "coffer"
# Default model for a fresh install. Requires an Anthropic key in the keychain;
# absent one, `send` returns 503 LLM_NOT_CONFIGURED until the user configures a
# provider (or switches the model to a local Ollama one).
DEFAULT_BUILTIN_MODEL = "anthropic:claude-sonnet-4-6"
# Conservative confirmation policy shipped on the seeded agent: destructive
# vault operations pause for human approval. Users may edit this freely.
DEFAULT_CONFIRM_TOOLS = ["*delete*", "*clear*", "*remove*", "*write*"]

OnDeleteHook = Callable[[ResourceRef], Awaitable[None] | None]


def make_builtin_agent_kind(on_delete: OnDeleteHook | None = None) -> Kind:
    return Kind(
        name=BUILTIN_AGENT_KIND,
        display_name="Built-in Agent",
        config_schema=BuiltinAgentConfig,
        on_delete=on_delete,
    )


async def ensure_default_builtin_agent(
    resource_service: ResourceService,
    *,
    actor: str = "system",
) -> Resource | None:
    """Seed a default built-in agent if none exists. Idempotent.

    Returns the freshly-seeded Resource, or ``None`` if one already existed.
    """
    existing = await resource_service.list(kind=BUILTIN_AGENT_KIND)
    if existing:
        return None
    cfg = BuiltinAgentConfig(
        model=DEFAULT_BUILTIN_MODEL,
        system_prompt=(
            "You are Coffer's built-in agent. You can use the tools Coffer's "
            "vault exposes (MCP servers, skills, knowledge bases, memory) to "
            "help the user. Be concise and cite which tool you used."
        ),
        confirm_tools=list(DEFAULT_CONFIRM_TOOLS),
    )
    return await resource_service.register(
        kind=BUILTIN_AGENT_KIND,
        name=DEFAULT_BUILTIN_NAME,
        config=cfg.model_dump(mode="json"),
        description="Coffer's built-in agent",
        actor=actor,
    )


def make_refuse_delete_last_hook(resource_service: ResourceService) -> OnDeleteHook:
    """Build an ``on_delete`` guard that refuses to remove the last built-in
    agent (so the chat surface always has a built-in target)."""

    from coffer.domain.errors import LastBuiltinAgent

    async def _hook(ref: ResourceRef) -> None:
        remaining = [
            r for r in await resource_service.list(kind=BUILTIN_AGENT_KIND) if r.name != ref.name
        ]
        if not remaining:
            raise LastBuiltinAgent()

    return _hook


# Re-exported so the composition root can record a distinct audit event if it
# wants; kept here to keep the seeding concern in one module.
SEED_EVENT = AuditEventType.RESOURCE_CREATED
