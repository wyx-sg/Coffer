"""Port (Protocol) definitions for the MCP application layer.

CODE-005: application code must depend on abstract Protocols, never on
infrastructure classes directly. The concrete implementations in
``coffer.infrastructure.{credentials,mcp}.*`` are wired at composition root
(``coffer.surfaces.http.app``) and pass through these Protocol types.

These mirror the existing concrete shapes — they exist so application
modules can import a stable port instead of an infrastructure class. The
contract is structural (Protocol), so the concrete adapters do NOT need to
subclass anything; they just need to satisfy the method signatures.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Protocol

from coffer.domain.mcp.capability import (
    CapabilityType,
    MCPCapabilityPreference,
    MCPInvocation,
)


class KeyringPort(Protocol):
    """OS-keychain bridge. Confined to infrastructure via importlinter Contract 4."""

    def get(self, ref: str) -> str | None: ...
    def set(self, ref: str, value: str) -> None: ...
    def delete(self, ref: str) -> None: ...


class UpstreamConnectionPort(Protocol):
    """One open upstream MCP session — stdio or HTTP/SSE.

    Mirrored from the existing concrete shape in
    ``coffer.infrastructure.mcp.{subprocess,http_client}``.
    """

    async def spawn_and_initialize(self) -> dict[str, Any]: ...
    async def request(self, method: str, params: dict[str, Any]) -> Any: ...
    def on_notification(self, cb: Callable[[Any], Awaitable[None]]) -> None: ...
    def on_sampling_request(self, cb: Any) -> None: ...
    def on_roots_request(self, cb: Any) -> None: ...
    async def close(self) -> None: ...


class MCPCapabilityPreferenceRepoPort(Protocol):
    """Persisted user preferences (enabled/disabled per capability)."""

    async def find(
        self,
        resource_id: int,
        capability_type: CapabilityType,
        capability_key: str,
    ) -> MCPCapabilityPreference | None: ...
    async def list_for(
        self,
        resource_id: int,
        capability_type: CapabilityType | None = None,
    ) -> list[MCPCapabilityPreference]: ...
    async def insert(
        self,
        resource_id: int,
        capability_type: CapabilityType,
        capability_key: str,
        enabled: bool,
        first_seen_at: datetime,
        last_seen_at: datetime,
    ) -> MCPCapabilityPreference: ...
    async def set_enabled(
        self,
        resource_id: int,
        capability_type: CapabilityType,
        capability_key: str,
        enabled: bool,
    ) -> MCPCapabilityPreference | None: ...
    async def touch_last_seen(
        self,
        resource_id: int,
        capability_type: CapabilityType,
        capability_key: str,
        when: datetime,
    ) -> None: ...
    async def reconcile(
        self,
        resource_id: int,
        capability_type: CapabilityType,
        current_keys: list[str],
        *,
        default_enabled: bool,
        when: datetime,
    ) -> list[str]: ...


class MCPInvocationRepoPort(Protocol):
    """MCP tool/resource/prompt invocation log writer + reader."""

    async def insert(self, inv: MCPInvocation) -> None: ...
    async def query(
        self,
        *,
        resource_name: str | None = None,
        status: Any | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[MCPInvocation]: ...
