"""Read one resource or fetch one prompt for the MCP server page's row details.

Spec mcp-gateway "Preview a resource or a prompt from the server page". The
owner opening a row asks the server directly, on the management connection the
listings use: nothing is recorded as an agent's invocation, and a disabled row
can still be looked at. What comes back is shaped for reading, not relayed raw:
text is cut at :data:`PREVIEW_TEXT_LIMIT`, and a binary body is described by
its size, never sent.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
from dataclasses import dataclass, replace
from typing import Any

from mcp import MCPError

from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway_coerce import coerce_prompt_result, coerce_read_result
from coffer.domain.errors import UpstreamUnavailable

#: How much of one text body a preview carries; the rest is marked cut.
PREVIEW_TEXT_LIMIT = 64 * 1024

# The same ceiling the capabilities page has: a cold spawn fits under it.
_PREVIEW_TIMEOUT = 35.0


@dataclass(frozen=True)
class PreviewContent:
    """One body of a resource, or one message of a prompt."""

    kind: str  # "text", "blob", or a prompt content type ("image", "audio", ...)
    text: str | None = None
    truncated: bool = False
    size_bytes: int | None = None
    uri: str | None = None
    mime_type: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class Preview:
    """What the server answered: its contents, or the error it answered with."""

    contents: list[PreviewContent]
    description: str | None = None
    error: str | None = None


def _cut(text: str) -> tuple[str, bool]:
    if len(text) <= PREVIEW_TEXT_LIMIT:
        return text, False
    return text[:PREVIEW_TEXT_LIMIT], True


def _blob_size(blob: str) -> int | None:
    try:
        return len(base64.b64decode(blob, validate=False))
    except (binascii.Error, ValueError):
        return None


def _body(raw: dict[str, Any], **extra: Any) -> PreviewContent:
    uri = raw.get("uri")
    mime = raw.get("mimeType")
    if isinstance(raw.get("text"), str):
        text, cut = _cut(raw["text"])
        return PreviewContent("text", text, cut, uri=uri, mime_type=mime, **extra)
    blob = raw.get("blob") or raw.get("data")
    size = _blob_size(blob) if isinstance(blob, str) else None
    return PreviewContent("blob", size_bytes=size, uri=uri, mime_type=mime, **extra)


def _message(raw: dict[str, Any]) -> PreviewContent:
    role = raw.get("role")
    content = raw.get("content") or {}
    kind = content.get("type", "text")
    if kind == "text":
        text, cut = _cut(str(content.get("text", "")))
        return PreviewContent("text", text, cut, role=role)
    if kind == "resource":
        return _body(content.get("resource") or {}, role=role)
    return replace(_body(content, role=role), kind=kind)


async def _ask(
    discovery: CapabilityDiscovery, server_name: str, method: str, params: dict[str, Any]
) -> Any:
    try:
        return await asyncio.wait_for(
            discovery.request(server_name, method, params), timeout=_PREVIEW_TIMEOUT
        )
    except TimeoutError as e:
        raise UpstreamUnavailable(
            f"{server_name!r} did not answer {method} within {_PREVIEW_TIMEOUT:.0f}s"
        ) from e


async def read_resource(discovery: CapabilityDiscovery, server_name: str, uri: str) -> Preview:
    """The resource ``uri`` names, read from ``server_name`` now."""
    try:
        result = coerce_read_result(
            await _ask(discovery, server_name, "resources/read", {"uri": uri})
        )
    except MCPError as e:
        return Preview(contents=[], error=str(e))
    return Preview(contents=[_body(c) for c in result.get("contents") or []])


async def get_prompt(
    discovery: CapabilityDiscovery,
    server_name: str,
    name: str,
    arguments: dict[str, str],
) -> Preview:
    """The prompt ``name`` filled with ``arguments``, as ``server_name`` renders it now."""
    params = {"name": name, "arguments": arguments or None}
    try:
        result = coerce_prompt_result(await _ask(discovery, server_name, "prompts/get", params))
    except MCPError as e:
        return Preview(contents=[], error=str(e))
    return Preview(
        contents=[_message(m) for m in result.get("messages") or []],
        description=result.get("description"),
    )
