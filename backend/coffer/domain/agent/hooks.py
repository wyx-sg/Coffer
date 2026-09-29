"""Reading an agent's native hooks, read only (spec agent-registry "List every
hook in the agent's native config").

Both shipped agents keep hooks in the same JSON shape — Claude Code in its
``settings.json`` / ``settings.local.json`` and in each plugin's
``hooks/hooks.json``, Codex in its ``hooks.json``::

    {"hooks": {"<Event>": [{"matcher": "...", "hooks": [{"type": "command",
                                                         "command": "..."}]}]}}

This module turns such a document into flat rows. It never writes, and it
judges nothing: which row is Coffer's own, and whether that one is current, is
the delivery hook's knowledge (the projection facet), asked by the caller.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class HookSource(StrEnum):
    """Where a hook was found. ``user`` is a file in the agent's config
    directory; ``plugin`` is an installed, enabled plugin's hook file. A
    project's own settings are not read: Coffer does not know which
    repositories the agent is used in."""

    USER = "user"
    PLUGIN = "plugin"


class HookHealth(StrEnum):
    """Coffer's own delivery hook: ``current`` is exactly the command Coffer
    would write now; ``stale`` carries Coffer's marker with another command (an
    older build's); ``missing`` is not there at all."""

    CURRENT = "current"
    STALE = "stale"
    MISSING = "missing"


class MalformedHooks(ValueError):  # noqa: N818
    """A hook file that is not the JSON object shape above. Never reaches a
    caller of the hooks listing: it becomes a parse error beside the rows the
    other files yield."""


@dataclass(frozen=True)
class HookRow:
    """One command hook as the file declares it."""

    event: str
    matcher: str | None
    command: str
    type: str
    timeout: int | None


def _rows(event: str, groups: Any) -> list[HookRow]:
    rows: list[HookRow] = []
    if not isinstance(groups, list):
        return rows
    for group in groups:
        if not isinstance(group, dict):
            continue
        matcher = group.get("matcher")
        leaves = group.get("hooks")
        if not isinstance(leaves, list):
            continue
        for leaf in leaves:
            if not isinstance(leaf, dict):
                continue
            command = leaf.get("command")
            if not isinstance(command, str):
                continue
            timeout = leaf.get("timeout")
            rows.append(
                HookRow(
                    event=event,
                    matcher=matcher if isinstance(matcher, str) and matcher else None,
                    command=command,
                    type=str(leaf.get("type") or "command"),
                    timeout=timeout if isinstance(timeout, int) else None,
                )
            )
    return rows


def parse_hooks(text: str) -> list[HookRow]:
    """Every hook in a hook-carrying document, in file order. An empty file is
    no hooks; a file that is not a JSON object raises :class:`MalformedHooks`."""
    if not text.strip():
        return []
    try:
        data = json.loads(text)
    except ValueError as e:
        raise MalformedHooks(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise MalformedHooks("top-level value must be a JSON object")
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return []
    rows: list[HookRow] = []
    for event, groups in hooks.items():
        rows.extend(_rows(str(event), groups))
    return rows


__all__ = ["HookHealth", "HookRow", "HookSource", "MalformedHooks", "parse_hooks"]
