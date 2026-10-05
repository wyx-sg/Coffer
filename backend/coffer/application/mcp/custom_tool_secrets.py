"""Resolve one custom-tool environment's secrets, for one call or one test.

Spec mcp-gateway "Wait for approval before a custom tool sends its secret";
design align-cli-with-ui-and-add-tool-environments D6. The guarded resolver is
asked for exactly the chosen environment's refs, for that environment's
destination, so a missing value or a pending approval elsewhere in the group
changes nothing for this call. Shared by the gateway's connection (through the
supervisor) and the Custom tools page's and the CLI's tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from coffer.application.secret.resolver import SecretResolver
from coffer.domain.mcp.http_api_environment import HttpApiEnvironment
from coffer.domain.mcp.secret_target import environment_destination
from coffer.domain.resource import Resource

EnvSecrets = Callable[[HttpApiEnvironment], Awaitable[dict[str, str]]]


def env_secret_resolver(resolver: SecretResolver, resource: Resource) -> EnvSecrets:
    """``env -> {header: value}`` for ``resource``'s environments."""

    async def resolve(env: HttpApiEnvironment) -> dict[str, str]:
        if not env.secret_refs:
            return {}
        values = await asyncio.to_thread(
            resolver.materialize,
            env.slot_refs(),
            environment_destination(resource.uid, resource.name, env),
        )
        return {env.header_of(slot): value for slot, value in values.items()}

    return resolve


__all__ = ["EnvSecrets", "env_secret_resolver"]
