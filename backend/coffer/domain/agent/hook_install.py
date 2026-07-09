"""Build / detect / remove Coffer's lifecycle hook entries in an agent's config.

Pure domain text transforms — no filesystem access. The application layer reads
the agent's hooks file, calls one of these to produce new text, and writes it
back through the atomic store.

Two on-disk shapes exist, discriminated by :class:`HookFlavor` (see
``context_injection`` for the exact JSON of each). Both nest under a top-level
``hooks`` object keyed by event name; they differ in whether an event's list
holds matcher *groups* (Claude Code, Codex) or flat *command* entries (Cursor),
and in how the event is spelled.

Coffer recognises *its own* entry by the command basename ``coffer-hook`` — the
installed command is an absolute path plus ``--agent <name>``, and for a non-Claude
flavor also ``--dialect <flavor> --event <key>``. Only ``argv[0]``'s basename is
matched, so the args may grow without breaking recognition. User-authored hook
entries for the same event are never touched.
"""

from __future__ import annotations

import json
import os
import shlex
from collections.abc import Mapping, MutableMapping
from typing import Any

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.context_injection import (
    CURSOR_SCHEMA_VERSION,
    HOOK_CONTAINER_KEY,
    HookEvent,
    HookFlavor,
    event_key,
)
from coffer.domain.agent.mcp_entries import _parse_json

#: Basename that marks an entry as Coffer's own (vs a user-authored hook).
COFFER_HOOK_BASENAME = "coffer-hook"

#: The ``matcher`` Coffer registers per event, for the matcher-group flavor (the
#: union of trigger sources the external hook contract recognises for that event).
_MATCHERS: dict[HookEvent, str] = {
    HookEvent.SESSION_START: "startup|resume|clear|compact",
    HookEvent.SESSION_END: "clear|logout|prompt_input_exit|other",
}


def _is_coffer_command(cmd: str | None) -> bool:
    """Whether ``cmd`` invokes Coffer's own hook binary.

    ``cmd`` may be user-authored and arbitrarily malformed — an unbalanced quote
    makes ``shlex.split`` raise. Such a command is by definition not ours (Coffer
    shell-quotes every part of the command it installs), so a parse failure is a
    ``False``, never a crash: this runs in the daemon, outside ``coffer-hook``'s
    failure-is-silent wrapper, and a raise here would 500 install/uninstall/status
    for an agent whose hooks file merely contains someone else's odd quoting.
    """
    if cmd is None:
        return False
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return False
    argv0 = parts[0] if parts else cmd
    return os.path.basename(argv0) == COFFER_HOOK_BASENAME


def _entry_command(entry: Any) -> str | None:
    """The ``command`` string of a hook leaf, or ``None`` if not a command leaf."""
    if not isinstance(entry, MutableMapping):
        return None
    cmd = entry.get("command")
    return str(cmd) if cmd is not None else None


def _is_coffer_entry(entry: Any, flavor: HookFlavor) -> bool:
    """Whether one entry in an event's list was installed by Coffer.

    ``CURSOR`` entries carry the command directly; ``CLAUDE`` entries are matcher
    groups whose ``hooks`` leaves carry it.
    """
    if flavor is HookFlavor.CURSOR:
        return _is_coffer_command(_entry_command(entry))
    if not isinstance(entry, MutableMapping):
        return False
    leaves = entry.get("hooks")
    if not isinstance(leaves, (list, tuple)):
        return False
    return any(_is_coffer_command(_entry_command(leaf)) for leaf in leaves)


def _coffer_entry(command: str, event: HookEvent, flavor: HookFlavor) -> dict[str, Any]:
    if flavor is HookFlavor.CURSOR:
        return {"command": command}
    return {
        "matcher": _MATCHERS[event],
        "hooks": [{"type": "command", "command": command}],
    }


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def apply_install(
    content: str,
    *,
    commands: Mapping[HookEvent, str],
    events: tuple[HookEvent, ...],
    fmt: ConfigFileFormat,
    flavor: HookFlavor = HookFlavor.CLAUDE,
) -> str:
    """Return new hooks text with Coffer's ``coffer-hook`` entry for each event.

    ``commands`` maps each event to the exact command string to install. It is
    per-event because Cursor's hooks file keys entries by event but its stdin
    payload is not guaranteed to name the event, so the event is baked into the
    command's args; Claude/Codex read the event from stdin and so map every event
    to the same command.

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

    # Cursor's schema carries a version at the top level. Only supply it when
    # creating the key — an existing value is the user's (or a newer Cursor's).
    if flavor is HookFlavor.CURSOR and "version" not in data:
        data["version"] = CURSOR_SCHEMA_VERSION

    for event in events:
        key = event_key(flavor, event)
        entries = hooks.get(key)
        if not isinstance(entries, list):
            entries = []
        # Drop any prior coffer entry, keep user-authored ones, append fresh.
        kept = [e for e in entries if not _is_coffer_entry(e, flavor)]
        kept.append(_coffer_entry(commands[event], event, flavor))
        hooks[key] = kept

    return _dump(data)


def apply_uninstall(
    content: str,
    *,
    events: tuple[HookEvent, ...],
    fmt: ConfigFileFormat,
    flavor: HookFlavor = HookFlavor.CLAUDE,
) -> str:
    """Return new hooks text with ONLY Coffer's entries removed.

    User-authored hooks and unrelated keys are left intact. Now-empty event
    arrays and an empty top-level ``hooks`` object are dropped cleanly.

    Cursor's top-level ``version`` describes the file, not our entry, so it
    survives alongside any other content. But when removing our hooks empties the
    document down to ``version`` alone, that ``version`` is one ``apply_install``
    wrote into a file that had none — leaving it behind would mean uninstall does
    not undo install. So an otherwise-empty document is emptied completely.
    """
    assert fmt is ConfigFileFormat.JSON, f"hook uninstall unsupported for format {fmt!r}"
    data = _parse_json(content)
    hooks = data.get(HOOK_CONTAINER_KEY)
    if not isinstance(hooks, dict):
        return _dump(data)

    for event in events:
        key = event_key(flavor, event)
        entries = hooks.get(key)
        if not isinstance(entries, list):
            continue
        kept = [e for e in entries if not _is_coffer_entry(e, flavor)]
        if kept:
            hooks[key] = kept
        else:
            del hooks[key]

    if not hooks:
        del data[HOOK_CONTAINER_KEY]

    # Only our own `version` can be all that remains — see the docstring.
    if flavor is HookFlavor.CURSOR and set(data) == {"version"}:
        del data["version"]

    return _dump(data)


def is_installed(
    content: str,
    *,
    events: tuple[HookEvent, ...],
    fmt: ConfigFileFormat,
    flavor: HookFlavor = HookFlavor.CLAUDE,
) -> bool:
    """Whether Coffer's ``coffer-hook`` entry is present for every given event."""
    assert fmt is ConfigFileFormat.JSON, f"hook status unsupported for format {fmt!r}"
    if not content.strip():
        return False
    hooks = _parse_json(content).get(HOOK_CONTAINER_KEY)
    if not isinstance(hooks, dict):
        return False
    for event in events:
        entries = hooks.get(event_key(flavor, event))
        if not isinstance(entries, list) or not any(_is_coffer_entry(e, flavor) for e in entries):
            return False
    return True
