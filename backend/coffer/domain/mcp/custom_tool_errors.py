"""Errors of the custom-tool slice of the MCP kind; surfaces map codes to statuses."""

from __future__ import annotations

from typing import Literal

from coffer.domain.error_base import CofferError
from coffer.domain.handoff import Handoff, render_handoff


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


class OpenApiUnreadable(CofferError):  # noqa: N818
    """An OpenAPI document that could not be fetched, parsed or read.

    A parse failure says where it broke: ``line`` and ``column`` (1-based) go
    out as error details so the import dialog can show the text around it."""

    code = "OPENAPI_UNREADABLE"

    def __init__(self, message: str, *, line: int | None = None, column: int | None = None) -> None:
        super().__init__(message)
        self.error_details: dict[str, object] = {}
        if line is not None:
            self.error_details["line"] = line
        if column is not None:
            self.error_details["column"] = column


#: Why a spec URL could not be reached.
UnreachableReason = Literal["dns", "refused", "timeout", "unreachable"]


class OpenApiUnreachable(CofferError):  # noqa: N818
    """A spec URL that did not answer: DNS, a refused connection or a timeout.

    Depends on this machine's network, so the details carry a hand-off prompt
    for the person's agent."""

    code = "OPENAPI_UNREACHABLE"

    def __init__(self, url: str, reason: UnreachableReason) -> None:
        said = {
            "dns": "the host name could not be resolved",
            "refused": "the connection was refused",
            "timeout": "the request timed out",
            "unreachable": "the host could not be reached",
        }[reason]
        super().__init__(f"could not reach {url}: {said}")
        self.reason = reason
        prompt = render_handoff(
            Handoff(
                task="Coffer could not fetch an OpenAPI spec from a URL. Find out why and fix it.",
                facts=(f"URL: {url}", f"Failure: {said}"),
                steps=(
                    "Check that the URL is spelled correctly and the host is up.",
                    "Check this machine's network, VPN and proxy settings against that host.",
                    "Confirm it worked by fetching the URL here and getting the spec back.",
                ),
            )
        )
        self.error_details: dict[str, object] = {"handoff": {"prompt": prompt}}


class NotImportedFromOpenApi(CofferError):  # noqa: N818
    code = "NOT_IMPORTED_FROM_OPENAPI"

    def __init__(self, name: str) -> None:
        super().__init__(f"custom-tool group {name!r} was not imported from an OpenAPI document")


class OpenApiFileNeeded(CofferError):  # noqa: N818
    code = "OPENAPI_FILE_NEEDED"

    def __init__(self, name: str) -> None:
        super().__init__(
            f"custom-tool group {name!r} was imported from a file; give the file again to re-import"
        )
