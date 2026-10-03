"""The interface of a command-line tool, as its own help describes it (spec
skill-manager "Serve required commands on REST and the web").

A :class:`HelpNode` is one command in the tree — the tool itself (empty
``path``) or one of its subcommands — with what its ``--help`` printed parsed
into a usage line, a description, subcommands, options and positional
arguments. ``raw`` is always kept: a help text the parser cannot structure
(``structured`` false) is still shown as it was printed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DiscoveryStatus(StrEnum):
    #: Nothing has been read for this version of the tool yet.
    NOT_READ = "not_read"
    OK = "ok"
    #: The tool is missing, so there is nothing to read.
    UNAVAILABLE = "unavailable"
    #: The tool printed no help for ``--help`` / ``-h``.
    NO_HELP = "no_help"


@dataclass(frozen=True)
class HelpOption:
    #: ``("-o", "--output")``: every spelling, as printed.
    names: tuple[str, ...]
    metavar: str | None = None
    description: str | None = None
    default: str | None = None
    required: bool = False


@dataclass(frozen=True)
class HelpArgument:
    name: str
    description: str | None = None
    required: bool = False


@dataclass(frozen=True)
class HelpSubcommand:
    name: str
    summary: str | None = None


@dataclass(frozen=True)
class HelpNode:
    #: Subcommand names from the tool down; ``()`` for the tool itself.
    path: tuple[str, ...]
    usage: str | None = None
    description: str | None = None
    subcommands: tuple[HelpSubcommand, ...] = ()
    options: tuple[HelpOption, ...] = ()
    arguments: tuple[HelpArgument, ...] = ()
    raw: str = ""
    structured: bool = False
    #: Why this node has no help (timed out, not found), when it has none.
    error: str | None = None
    #: The raw text was cut at the output cap.
    truncated: bool = False


@dataclass(frozen=True)
class Interface:
    status: DiscoveryStatus
    nodes: tuple[HelpNode, ...] = ()
    discovered_at: datetime | None = None
    #: The tree was cut by the depth, node or time bound.
    incomplete: bool = False
    message: str | None = None
    #: What the tree was read from; a different key is a different tree.
    key: str | None = None
    version: str | None = None


__all__ = [
    "DiscoveryStatus",
    "HelpArgument",
    "HelpNode",
    "HelpOption",
    "HelpSubcommand",
    "Interface",
]
