"""Router dependency: let an agent's TYPE stand where its uid goes.

There is one agent per type, named by it (spec agent-registry "Keep one agent
per type, named by it"), so ``/api/v1/agents/claude-code/...`` — or
``claude_code`` — addresses the same agent as its uid. Router-level
dependencies are solved before a route's path parameters are read, so
rewriting ``{uid}`` here hands every handler below the uid it already expects:
one translation at the edge instead of one per route.

Kind-agnostic on purpose: it asks the resource registry for the ``agent`` row
carrying that name, so the skill-owned router under ``/api/v1/agents`` can use
it without importing the agent kind. A value that names no agent — a uid, or a
type with no agent registered — is left as written; the route then reads it as
a uid and answers not found for a type that is not registered.
"""

from __future__ import annotations

from fastapi import Request

from coffer.surfaces.http.dependencies import get_resource_service


async def resolve_agent_path(request: Request) -> None:
    ref = request.path_params.get("uid")
    if not isinstance(ref, str) or not ref:
        return
    # An agent's name is its type's with hyphens (``claude-code``); the type's
    # value (``claude_code``) reads the same.
    name = ref.replace("_", "-")
    provider = request.app.dependency_overrides.get(get_resource_service, get_resource_service)
    for row in await provider().list(kind="agent"):
        if row.name == name:
            request.path_params["uid"] = row.uid
            return


__all__ = ["resolve_agent_path"]
