"""Errors of a custom tool's environments and arguments; surfaces map codes to statuses.

Spec mcp-gateway "Choose a custom tool's environment on every call" and
"Validate a custom tool's arguments before any request".
"""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class CustomToolEnvironmentRequired(CofferError):  # noqa: N818
    code = "CUSTOM_TOOL_ENVIRONMENT_REQUIRED"

    def __init__(self, group: str, enabled: list[str]) -> None:
        names = ", ".join(enabled) or "none is switched on"
        super().__init__(
            f"custom-tool group {group!r} has several environments; name one in "
            f"'coffer_environment' ({names})"
        )
        self.error_details: dict[str, object] = {"group": group, "environments": enabled}


class CustomToolEnvironmentUnknown(CofferError):  # noqa: N818
    code = "CUSTOM_TOOL_ENVIRONMENT_UNKNOWN"

    def __init__(self, group: str, name: str, enabled: list[str]) -> None:
        super().__init__(
            f"custom-tool group {group!r} has no environment {name!r}; "
            f"choose one of: {', '.join(enabled) or 'none is switched on'}"
        )
        self.error_details: dict[str, object] = {
            "group": group,
            "environment": name,
            "environments": enabled,
        }


class CustomToolEnvironmentDisabled(CofferError):  # noqa: N818
    code = "CUSTOM_TOOL_ENVIRONMENT_DISABLED"

    def __init__(self, group: str, name: str) -> None:
        super().__init__(f"environment {name!r} of custom-tool group {group!r} is switched off")
        self.error_details: dict[str, object] = {"group": group, "environment": name}


class CustomToolEnvironmentNotFound(CofferError):  # noqa: N818
    """A management request naming an environment the group does not have."""

    code = "CUSTOM_TOOL_ENVIRONMENT_NOT_FOUND"

    def __init__(self, group: str, name: str) -> None:
        super().__init__(f"custom-tool group {group!r} has no environment {name!r}")


class CustomToolEnvironmentExists(CofferError):  # noqa: N818
    code = "CUSTOM_TOOL_ENVIRONMENT_EXISTS"

    def __init__(self, group: str, name: str) -> None:
        super().__init__(f"custom-tool group {group!r} already has an environment {name!r}")


class CustomToolLastEnvironment(CofferError):  # noqa: N818
    code = "CUSTOM_TOOL_LAST_ENVIRONMENT"

    def __init__(self, group: str) -> None:
        super().__init__(f"custom-tool group {group!r} needs at least one environment")


__all__ = [
    "CustomToolEnvironmentDisabled",
    "CustomToolEnvironmentExists",
    "CustomToolEnvironmentNotFound",
    "CustomToolEnvironmentRequired",
    "CustomToolEnvironmentUnknown",
    "CustomToolLastEnvironment",
]
