"""Refusals of the required-command surfaces (spec skill-manager "Serve
required commands on REST, the command line and the web")."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class CliNotRequired(CofferError):  # noqa: N818
    """No managed skill or MCP server requires this command. Maps to 404."""

    code = "CLI_NOT_REQUIRED"

    def __init__(self, command: str) -> None:
        super().__init__(f"no skill or MCP server requires the command {command!r}")
        self.command = command


__all__ = ["CliNotRequired"]
