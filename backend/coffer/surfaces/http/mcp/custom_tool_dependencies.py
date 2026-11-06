"""Dependency providers of the custom tools routes (the MCP kind's own)."""

from __future__ import annotations

from coffer.application.mcp.custom_tool_environments import CustomToolEnvironments
from coffer.application.mcp.custom_tool_preview import CustomToolPreviews
from coffer.application.mcp.custom_tools import CustomToolService

_service: CustomToolService | None = None


def set_custom_tool_services(service: CustomToolService | None) -> None:
    """Called once by the composition root (and by tests)."""
    global _service
    _service = service


def get_custom_tool_service() -> CustomToolService:
    if _service is None:
        raise RuntimeError("custom tool service not initialised")
    return _service


def get_custom_tool_environments() -> CustomToolEnvironments:
    """The environment operations, over the one service's write path."""
    return CustomToolEnvironments(get_custom_tool_service())


def get_custom_tool_previews() -> CustomToolPreviews:
    """Dry runs of a tool's request, over the one service's checks."""
    return CustomToolPreviews(get_custom_tool_service())
