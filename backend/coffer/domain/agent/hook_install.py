"""Build / detect / remove Coffer's lifecycle hook entries in an agent's config.

Pure domain text transforms — no filesystem access. The application layer reads
the agent's hooks file, calls one of these to produce new text, and writes it
back through the atomic store.

Both Claude Code (``settings.json``) and Codex (``hooks.json``) use the same
JSON shape: a top-level ``hooks`` object keyed by event name, each value a list
of entries ``{ "matcher": ..., "hooks": [ {"type": "command", "command": ...} ] }``.

Coffer recognises *its own* entry by the command basename ``coffer-hook`` (the
installed command is an absolute path plus ``--agent <name>`` args). User-authored
hook entries for the same event are never touched.
"""

from __future__ import annotations

import json
import os
import shlex
from collections.abc import MutableMapping
from typing import Any

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.hook_injection import HOOK_CONTAINER_KEY, HookEvent
from coffer.domain.agent.mcp_entries import _parse_json

#: Basename that marks an entry as Coffer's own (vs a user-authored hook).
COFFER_HOOK_BASENAME = "coffer-hook"

#: The ``matcher`` Coffer registers per event (the union of trigger sources the
#: external hook contract recognises for that event).
_MATCHERS: dict[HookEvent, str] = {
    HookEvent.SESSION_START: "startup|resume|clear|compact",
    HookEvent.SESSION_END: "clear|logout|prompt_input_exit|other",
}


def _entry_command(entry: Any) -> str | None:
    """The ``command`` string of a hook leaf, or ``None`` if not a command leaf."""
    if not isinstance(entry, MutableMapping):
        return None
    cmd = entry.get("command")
    return str(cmd) if cmd is not None else None


def _is_coffer_group(group: Any) -> bool:
    """Whether a matcher-group entry was installed by Coffer.

    A group is Coffer's if any of its ``hooks`` leaves runs a command whose
    executable basename is ``coffer-hook``.
    """
    if not isinstance(group, MutableMapping):
        return False
    leaves = group.get("hooks")
    if not isinstance(leaves, (list, tuple)):
        return False
    for leaf in leaves:
        cmd = _entry_command(leaf)
        if cmd is None:
            continue
        parts = shlex.split(cmd)
        argv0 = parts[0] if parts else cmd
        if os.path.basename(argv0) == COFFER_HOOK_BASENAME:
            return True
    return False


def _coffer_group(command: str, event: HookEvent) -> dict[str, Any]:
    return {
        "matcher": _MATCHERS[event],
        "hooks": [{"type": "command", "command": command}],
    }


def apply_install(
    content: str,
    *,
    command: str,
    events: tuple[HookEvent, ...],
    fmt: ConfigFileFormat,
) -> str:
    """Return new hooks text with Coffer's ``coffer-hook`` entry for each event.

    Idempotent: Coffer's existing entry (recognised by the ``coffer-hook``
    basename) is replaced in place; user-authored hooks for the same event are
    preserved.
    """
    assert fmt is ConfigFileFormat.JSON, f"hook install unsupported for format {fmt!r}"
    data = _parse_json(content)
    hooks = data.get(HOOK_CONTAINER_KEY)
    if not isinstance(hooks, dict):
        hooks = {}
        data[HOOK_CONTAINER_KEY] = hooks

    for event in events:
        groups = hooks.get(event.value)
        if not isinstance(groups, list):
            groups = []
        # Drop any prior coffer group, keep user-authored ones, append fresh.
        kept = [g for g in groups if not _is_coffer_group(g)]
        kept.append(_coffer_group(command, event))
        hooks[event.value] = kept

    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def apply_uninstall(
    content: str,
    *,
    events: tuple[HookEvent, ...],
    fmt: ConfigFileFormat,
) -> str:
    """Return new hooks text with ONLY Coffer's entries removed.

    User-authored hooks and unrelated keys are left intact. Now-empty event
    arrays and an empty top-level ``hooks`` object are dropped cleanly.
    """
    assert fmt is ConfigFileFormat.JSON, f"hook uninstall unsupported for format {fmt!r}"
    data = _parse_json(content)
    hooks = data.get(HOOK_CONTAINER_KEY)
    if not isinstance(hooks, dict):
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    for event in events:
        groups = hooks.get(event.value)
        if not isinstance(groups, list):
            continue
        kept = [g for g in groups if not _is_coffer_group(g)]
        if kept:
            hooks[event.value] = kept
        else:
            del hooks[event.value]

    if not hooks:
        del data[HOOK_CONTAINER_KEY]

    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def is_installed(
    content: str,
    *,
    events: tuple[HookEvent, ...],
    fmt: ConfigFileFormat,
) -> bool:
    """Whether Coffer's ``coffer-hook`` entry is present for every given event."""
    assert fmt is ConfigFileFormat.JSON, f"hook status unsupported for format {fmt!r}"
    if not content.strip():
        return False
    hooks = _parse_json(content).get(HOOK_CONTAINER_KEY)
    if not isinstance(hooks, dict):
        return False
    for event in events:
        groups = hooks.get(event.value)
        if not isinstance(groups, list) or not any(_is_coffer_group(g) for g in groups):
            return False
    return True
