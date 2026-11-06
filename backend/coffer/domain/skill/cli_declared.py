"""A command-line tool the person declared by hand (spec skill-manager
"Declare a command-line tool without a skill").

No skill or MCP server is involved: the person names a command, and may give
it a title, a description and a minimum version. The declaration is
machine-independent (it travels with the vault); where the command is found on
one machine is machine-local and not part of it. Coffer runs only
``<command> --version`` for it.

A stored entry from an older build may still carry ``login_check``; it is not
read, and the next write of the document drops it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from coffer.domain.error_base import CofferError
from coffer.domain.skill.requirements import COMMAND_RE

_MIN_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")
TEXT_MAX = 200
DESCRIPTION_MAX = 1000
#: Most tools one vault declares; a cap, not a target.
MAX_DECLARED = 200


class CliToolInvalid(CofferError):  # noqa: N818
    """A declaration that cannot be used. Maps to 400."""

    code = "CLI_TOOL_INVALID"


class CliToolExists(CofferError):  # noqa: N818
    """The command is already declared by hand. Maps to 409."""

    code = "CLI_TOOL_EXISTS"

    def __init__(self, command: str) -> None:
        super().__init__(f"the command-line tool {command!r} is already added")
        self.command = command


class CliToolNotDeclared(CofferError):  # noqa: N818
    """No tool of this name was added by hand. Maps to 404."""

    code = "CLI_TOOL_NOT_DECLARED"

    def __init__(self, command: str) -> None:
        super().__init__(f"the command-line tool {command!r} was not added by hand")
        self.command = command


@dataclass(frozen=True)
class DeclaredTool:
    command: str
    title: str | None = None
    description: str | None = None
    min_version: str | None = None


def is_path(raw: str) -> bool:
    return raw.strip().startswith("/")


def command_name(raw: str) -> str:
    """The command name of ``raw``: a bare name, or the file name of an
    absolute path."""
    text = raw.strip()
    name = text.rsplit("/", 1)[-1] if is_path(text) else text
    if not COMMAND_RE.match(name):
        raise CliToolInvalid(f"{raw!r} is not a command name or an absolute path")
    return name


def clean_text(value: str | None, field: str, limit: int = TEXT_MAX) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    if not text:
        return None
    if len(text) > limit:
        raise CliToolInvalid(f"{field} is longer than {limit} characters")
    return text


def clean_min_version(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    text = value.strip().lstrip(">=~ ")
    if not _MIN_VERSION_RE.match(text):
        raise CliToolInvalid(f"minimum version {value!r} is not dotted numbers, like 2.40")
    return text


def to_document(tool: DeclaredTool) -> dict[str, Any]:
    return {
        "command": tool.command,
        "title": tool.title,
        "description": tool.description,
        "min_version": tool.min_version,
    }


def from_document(entry: Any) -> DeclaredTool | None:
    """The tool a stored entry describes; ``None`` for one that is not usable
    (hand-edited, or from a newer build)."""
    if not isinstance(entry, dict):
        return None
    command = entry.get("command")
    if not isinstance(command, str) or not COMMAND_RE.match(command):
        return None

    def text(key: str) -> str | None:
        raw = entry.get(key)
        return raw if isinstance(raw, str) and raw else None

    return DeclaredTool(command, text("title"), text("description"), text("min_version"))


__all__ = [
    "DESCRIPTION_MAX",
    "MAX_DECLARED",
    "CliToolExists",
    "CliToolInvalid",
    "CliToolNotDeclared",
    "DeclaredTool",
    "clean_min_version",
    "clean_text",
    "command_name",
    "from_document",
    "is_path",
    "to_document",
]
