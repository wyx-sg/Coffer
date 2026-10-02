"""Refusals of the command-line tool surfaces (spec skill-manager "Serve
required commands on REST, the command line and the web")."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class CliNotKnown(CofferError):  # noqa: N818
    """Nothing declares this command: no managed skill, no enabled MCP server
    and no tool added by hand. Maps to 404."""

    code = "CLI_NOT_KNOWN"

    def __init__(self, command: str) -> None:
        super().__init__(f"{command!r} is not a command-line tool Coffer knows")
        self.command = command


__all__ = ["CliNotKnown"]
