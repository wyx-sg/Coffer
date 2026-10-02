"""The interface read from a tool's help, kept on this machine.

One JSON file per command under ``local/cli-interfaces/``: machine-local and
never synced (the tool, its version and its path are this machine's), and
rebuildable by reading the help again, so a file that does not parse is simply
read as nothing. The raw help of each node is kept up to ``RAW_KEPT`` bytes
(it is what the parsed fields were read from, and the page can still show the
cut text with its marker).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from coffer.domain.skill.cli_help import (
    DiscoveryStatus,
    HelpArgument,
    HelpNode,
    HelpOption,
    HelpSubcommand,
    Interface,
)
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.json_store import JsonStore

RAW_KEPT = 64 * 1024


def _node_doc(n: HelpNode) -> dict[str, Any]:
    cut = len(n.raw) > RAW_KEPT
    return {
        "path": list(n.path),
        "usage": n.usage,
        "description": n.description,
        "subcommands": [[s.name, s.summary] for s in n.subcommands],
        "options": [
            [list(o.names), o.metavar, o.description, o.default, o.required] for o in n.options
        ],
        "arguments": [[a.name, a.description, a.required] for a in n.arguments],
        "raw": n.raw[:RAW_KEPT],
        "structured": n.structured,
        "error": n.error,
        "truncated": n.truncated or cut,
    }


def _node(d: dict[str, Any]) -> HelpNode:
    return HelpNode(
        path=tuple(d["path"]),
        usage=d["usage"],
        description=d["description"],
        subcommands=tuple(HelpSubcommand(*s) for s in d["subcommands"]),
        options=tuple(HelpOption(tuple(o[0]), *o[1:]) for o in d["options"]),
        arguments=tuple(HelpArgument(*a) for a in d["arguments"]),
        raw=d["raw"],
        structured=d["structured"],
        error=d["error"],
        truncated=d["truncated"],
    )


class LocalInterfaceStore:
    """``InterfaceStorePort`` over ``local/cli-interfaces/<command>.json``."""

    def __init__(self, *, home: Path | None = None) -> None:
        self._home = home

    def _store(self, command: str) -> JsonStore:
        return JsonStore(lambda: local_root(self._home) / "cli-interfaces" / f"{command}.json")

    def get(self, command: str) -> Interface | None:
        d = self._store(command).read()
        try:
            return Interface(
                DiscoveryStatus(d["status"]),
                tuple(_node(n) for n in d["nodes"]),
                datetime.fromisoformat(d["discovered_at"]) if d["discovered_at"] else None,
                d["incomplete"],
                d["message"],
                d["key"],
                d["version"],
            )
        except (KeyError, TypeError, ValueError, IndexError):
            return None

    def put(self, command: str, interface: Interface) -> None:
        self._store(command).write(
            {
                "status": interface.status.value,
                "nodes": [_node_doc(n) for n in interface.nodes],
                "discovered_at": interface.discovered_at.isoformat()
                if interface.discovered_at
                else None,
                "incomplete": interface.incomplete,
                "message": interface.message,
                "key": interface.key,
                "version": interface.version,
            }
        )


__all__ = ["RAW_KEPT", "LocalInterfaceStore"]
