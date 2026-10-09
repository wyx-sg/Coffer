"""The retired memory delivery hook: how to recognise and remove it.

Earlier builds installed two entries, on ``SessionStart`` and
``UserPromptSubmit``, into Claude Code's ``settings.json`` and Codex's
``hooks.json``. Each ran ``: coffer-memory; coffer memory hook ...``, so the
marker is the first word after the leading no-op. The upgrade step removes
every entry carrying it and leaves every other hook and key as it was (spec
memory "Remove the memory delivery hook on upgrade").

Pure: text in, text out.
"""

from __future__ import annotations

import json
from typing import Any

from coffer.domain.error_base import CofferError

#: The marker every entry Coffer installed carries.
MARKER = "coffer-memory"
#: The top-level key both formats keep their hooks under.
HOOKS_KEY = "hooks"


class MalformedHooksFile(CofferError):  # noqa: N818
    """The agent's hooks file is not a JSON object Coffer can edit; it is left
    as it is rather than clobbered."""

    code = "MEMORY_DELIVERY_CONFIG_INVALID"


def _parse(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError as e:
        raise MalformedHooksFile(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise MalformedHooksFile("top-level value must be a JSON object")
    return data


def _is_marked(command: str) -> bool:
    return command.startswith(f": {MARKER}")


def _is_coffer_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    leaves = entry.get("hooks")
    if not isinstance(leaves, list):
        return False
    return any(
        isinstance(leaf, dict)
        and isinstance(leaf.get("command"), str)
        and _is_marked(leaf["command"])
        for leaf in leaves
    )


def remove_entries(text: str) -> str | None:
    """``text`` with every Coffer-marked entry removed, or ``None`` when it
    holds none. An event left empty is dropped, and so is an empty ``hooks``."""
    data = _parse(text)
    hooks = data.get(HOOKS_KEY)
    if not isinstance(hooks, dict):
        return None
    changed = False
    for event in list(hooks):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        kept = [e for e in entries if not _is_coffer_entry(e)]
        if len(kept) == len(entries):
            continue
        changed = True
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not changed:
        return None
    if not hooks:
        del data[HOOKS_KEY]
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


__all__ = ["MARKER", "MalformedHooksFile", "remove_entries"]
