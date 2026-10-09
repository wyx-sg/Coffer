"""Writing one invocation row, and the capability switch read before a call.

Split from ``gateway_handlers`` for the 400-line guideline.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from coffer.application.mcp.ports import (
    MCPCapabilityPreferenceRepoPort,
    MCPInvocationRepoPort,
)
from coffer.application.runtime import correlation
from coffer.domain.errors import ToolDisabled
from coffer.domain.mcp.capability import CapabilityType, MCPInvocation


async def check_capability_enabled(
    prefs: MCPCapabilityPreferenceRepoPort,
    resource_uid: str,
    capability_type: CapabilityType,
    capability_key: str,
) -> None:
    """Raise ToolDisabled if the capability is switched off."""
    pref = await prefs.find(resource_uid, capability_type, capability_key)
    # Missing row → default to enabled (matches CapabilityDiscovery's behaviour).
    if pref is not None and not pref.enabled:
        raise ToolDisabled(f"{capability_type}:{capability_key!r} is disabled on this server")


async def record_invocation(
    invocations: MCPInvocationRepoPort,
    *,
    session_id: str,
    clock: Callable[[], datetime],
    agent_uid: str | None = None,
    resource_uid: str,
    capability_type: CapabilityType,
    capability_key: str,
    duration_ms: int,
    status: Literal["ok", "error", "timeout", "denied"],
    error_message: str | None,
    environment: str | None = None,
    content: dict[str, Any] | None = None,
) -> None:
    await invocations.insert(
        MCPInvocation(
            id=None,
            timestamp=clock(),
            resource_uid=resource_uid,
            capability_type=capability_type,
            capability_key=capability_key,
            duration_ms=duration_ms,
            status=status,
            error_message=error_message,
            session_id=session_id,
            agent_uid=agent_uid,
            trace_id=correlation.current().trace_id,
            environment=environment,
            content=content,
        )
    )
