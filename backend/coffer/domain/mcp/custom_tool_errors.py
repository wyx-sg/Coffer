"""Errors of the custom-tool slice of the MCP kind; surfaces map codes to statuses."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class CustomToolNotFound(CofferError):  # noqa: N818
    code = "CUSTOM_TOOL_NOT_FOUND"

    def __init__(self, group: str, tool: str) -> None:
        super().__init__(f"custom-tool group {group!r} has no tool {tool!r}")


class CustomToolExists(CofferError):  # noqa: N818
    code = "CUSTOM_TOOL_EXISTS"

    def __init__(self, group: str, tool: str) -> None:
        super().__init__(f"custom-tool group {group!r} already has a tool {tool!r}")


class NotACustomToolGroup(CofferError):  # noqa: N818
    """An MCP server of another transport addressed as a custom-tool group."""

    code = "NOT_A_CUSTOM_TOOL_GROUP"

    def __init__(self, name: str) -> None:
        super().__init__(f"MCP server {name!r} is not a custom-tool group")
