"""CompositeRuntimeFactory — picks the runtime for a conversation target.

Kept import-light: the heavy runtime modules (LangGraph engine; subprocess
driver) are imported lazily inside ``build`` so importing this module — and
wiring it at startup — never requires LangChain to be installed unless a
built-in turn is actually run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coffer.application.chat.ports import AgentRuntime
from coffer.domain.errors import NotAChatTarget
from coffer.domain.resource import ResourceRef

# Returns (gateway_url, token) for the built-in runtime's MCP connection.
GatewayEndpoint = Callable[[], tuple[str | None, str | None]]


class CompositeRuntimeFactory:
    def __init__(self, *, gateway_endpoint: GatewayEndpoint, keyring: Any) -> None:
        self._gateway_endpoint = gateway_endpoint
        self._keyring = keyring

    def build(self, *, target: ResourceRef, config: dict[str, Any]) -> AgentRuntime:
        if target.kind == "builtin_agent":
            from coffer.infrastructure.chat.builtin_runtime import BuiltinRuntime

            url, token = self._gateway_endpoint()
            return BuiltinRuntime(
                config=config,
                gateway_url=url,
                gateway_token=token,
                keyring=self._keyring,
            )
        if target.kind == "agent":
            from coffer.infrastructure.chat.external_runtime import ExternalAgentRuntime

            return ExternalAgentRuntime(config=config)
        raise NotAChatTarget(target.kind)
