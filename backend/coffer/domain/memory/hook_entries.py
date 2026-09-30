"""Coffer's entry in an agent's hooks document: the marker that identifies
it, and the pure text transforms that insert, find and remove it.

Both supported agents keep hooks in one JSON shape — Claude Code's
`settings.json`, Codex's `hooks.json` — an object under `hooks` keyed by
event name, each value a list of matcher groups. Every function here takes and
returns text, never a path; `domain.memory.delivery` re-exports them beside
the adapter Protocol that composes them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from coffer.domain.error_base import CofferError

#: Marks every hook entry Coffer installs. Embedded as the argument to a
#: leading no-op `:` shell command so it survives verbatim at the very start
#: of the installed command string regardless of what follows it (a bare
#: `coffer` or an absolute path to it, which a future packaging change may
#: move) — detection never depends on `argv[0]`.
MARKER = "coffer-memory"

#: The one top-level key both supported formats keep their hook entries
#: under (Claude Code's `settings.json`, Codex's `hooks.json`): an object
#: keyed by event name, each value a list of matcher groups.
HOOKS_KEY = "hooks"


class MalformedDeliveryConfig(CofferError):  # noqa: N818
    """The agent's settings/hooks file is not a JSON object Coffer can edit.

    Raised instead of silently clobbering content Coffer cannot parse — the
    caller (`application.memory.delivery`) re-raises this with the file's
    path attached, since a domain function never sees a path, only text.
    """

    code = "MEMORY_DELIVERY_CONFIG_INVALID"


@dataclass(frozen=True)
class InstalledHook:
    """Coffer's entry as found in an agent's hooks document: where it sits
    (which event, which matcher group, which handler in it) and what it says."""

    event: str
    command: str
    matcher: str | None
    group_index: int
    handler_index: int
    #: The handler object exactly as the file holds it.
    handler: dict[str, Any]


def _parse(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError as e:
        raise MalformedDeliveryConfig(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise MalformedDeliveryConfig("top-level value must be a JSON object")
    return data


def _dump(data: dict[str, Any]) -> str:
    # ensure_ascii=False: a settings file may hold non-ASCII content
    # (project paths, plugin names) elsewhere; escaping it on every install
    # would needlessly rewrite unrelated bytes. Mirrors mcp_install.py.
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _is_coffer_leaf(leaf: Any) -> bool:
    if not isinstance(leaf, dict):
        return False
    cmd = leaf.get("command")
    return isinstance(cmd, str) and is_marked(cmd)


def _is_coffer_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    leaves = entry.get("hooks")
    if not isinstance(leaves, list):
        return False
    return any(_is_coffer_leaf(leaf) for leaf in leaves)


def _drop_coffer_entries(hooks: dict[str, Any], *, keep_event: str | None = None) -> None:
    """Remove every Coffer-marked entry from every event in `hooks`, in place.

    Every event, not only the one this build installs on: an older build put
    Codex's hook on `UserPromptSubmit`, and a reinstall that looked only at
    `SessionStart` would leave that entry behind to fire (or fail) beside the
    new one. An event array left empty is dropped — except `keep_event`, which
    the caller is about to append to.
    """
    for event in list(hooks):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        kept = [e for e in entries if not _is_coffer_entry(e)]
        if len(kept) == len(entries):
            continue
        if kept or event == keep_event:
            hooks[event] = kept
        else:
            del hooks[event]


def install_entry(
    text: str,
    *,
    event: str,
    command: str,
    matcher: str | None,
    timeout: int | None = None,
) -> str:
    """Return `text` with Coffer's hook entry for `event` inserted/replaced.

    Idempotent: every prior Coffer entry — on `event` or on any other event an
    older build used — is dropped and one fresh entry carrying `command` is
    appended to `event`; every other entry — another event entirely, or a
    foreign hook on this SAME event — is left untouched.
    """
    data = _parse(text)
    hooks = data.get(HOOKS_KEY)
    if not isinstance(hooks, dict):
        hooks = {}
        data[HOOKS_KEY] = hooks
    _drop_coffer_entries(hooks, keep_event=event)
    entries = hooks.get(event)
    kept = list(entries) if isinstance(entries, list) else []
    leaf: dict[str, Any] = {"type": "command", "command": command}
    if timeout is not None:
        leaf["timeout"] = timeout
    new_entry: dict[str, Any] = {"hooks": [leaf]}
    if matcher is not None:
        new_entry = {"matcher": matcher, "hooks": [leaf]}
    kept.append(new_entry)
    hooks[event] = kept
    return _dump(data)


@dataclass(frozen=True)
class EntrySpec:
    """One entry Coffer wants on one event."""

    event: str
    command: str
    matcher: str | None
    timeout: int | None = None


def install_entries(text: str, entries: tuple[EntrySpec, ...]) -> str:
    """Return `text` with Coffer's entries set to exactly `entries`.

    Every prior Coffer entry, on any event, is dropped first; then one entry
    per spec is appended to its event. Foreign hooks on the same events, every
    other event and every unrelated key are left untouched. Idempotent.
    """
    data = _parse(text)
    hooks = data.get(HOOKS_KEY)
    if not isinstance(hooks, dict):
        hooks = {}
        data[HOOKS_KEY] = hooks
    _drop_coffer_entries(hooks)
    for spec in entries:
        existing = hooks.get(spec.event)
        kept = list(existing) if isinstance(existing, list) else []
        leaf: dict[str, Any] = {"type": "command", "command": spec.command}
        if spec.timeout is not None:
            leaf["timeout"] = spec.timeout
        entry: dict[str, Any] = {"hooks": [leaf]}
        if spec.matcher is not None:
            entry = {"matcher": spec.matcher, "hooks": [leaf]}
        kept.append(entry)
        hooks[spec.event] = kept
    return _dump(data)


def find_all_installed(text: str) -> list[InstalledHook]:
    """Every Coffer entry in `text`, on every event, in file order."""
    data = _parse(text)
    hooks = data.get(HOOKS_KEY)
    if not isinstance(hooks, dict):
        return []
    found: list[InstalledHook] = []
    for name, entries in hooks.items():
        if not isinstance(entries, list):
            continue
        for group_index, entry in enumerate(entries):
            if not _is_coffer_entry(entry):
                continue
            for handler_index, leaf in enumerate(entry.get("hooks", [])):
                if _is_coffer_leaf(leaf):
                    matcher = entry.get("matcher")
                    found.append(
                        InstalledHook(
                            event=str(name),
                            command=str(leaf.get("command")),
                            matcher=matcher if isinstance(matcher, str) else None,
                            group_index=group_index,
                            handler_index=handler_index,
                            handler=dict(leaf),
                        )
                    )
    return found


def remove_entry(text: str, *, event: str | None = None) -> str:
    """Return `text` with ONLY Coffer's entries removed — on `event`, or on
    every event when `event` is `None`.

    A foreign hook on the same event, every other event, and every unrelated
    top-level key are left intact. A now-empty event array is dropped
    cleanly, and so is an empty top-level `hooks` object — mirrors the
    removed injection layer's own cleanup behaviour.
    """
    data = _parse(text)
    hooks = data.get(HOOKS_KEY)
    if not isinstance(hooks, dict):
        return _dump(data)
    if event is None:
        _drop_coffer_entries(hooks)
    else:
        entries = hooks.get(event)
        if isinstance(entries, list):
            kept = [e for e in entries if not _is_coffer_entry(e)]
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
    if not hooks:
        del data[HOOKS_KEY]
    return _dump(data)


def find_installed(text: str, *, event: str | None = None) -> InstalledHook | None:
    """Coffer's entry — on `event`, or on the first event holding one when
    `event` is `None` — or `None` if absent."""
    data = _parse(text)
    hooks = data.get(HOOKS_KEY)
    if not isinstance(hooks, dict):
        return None
    events = [event] if event is not None else list(hooks)
    for name in events:
        entries = hooks.get(name)
        if not isinstance(entries, list):
            continue
        for group_index, entry in enumerate(entries):
            if not _is_coffer_entry(entry):
                continue
            for handler_index, leaf in enumerate(entry.get("hooks", [])):
                if _is_coffer_leaf(leaf):
                    matcher = entry.get("matcher")
                    return InstalledHook(
                        event=str(name),
                        command=str(leaf.get("command")),
                        matcher=matcher if isinstance(matcher, str) else None,
                        group_index=group_index,
                        handler_index=handler_index,
                        handler=dict(leaf),
                    )
    return None


def find_command(text: str, *, event: str | None = None) -> str | None:
    """The command of Coffer's entry (see :func:`find_installed`), or `None`."""
    found = find_installed(text, event=event)
    return found.command if found is not None else None


def is_marked(command: str) -> bool:
    """Whether a hook command carries Coffer's marker."""
    return command.startswith(f": {MARKER}")


def is_installed(text: str, *, event: str | None = None) -> bool:
    """Whether Coffer's entry is present in `text`."""
    return find_command(text, event=event) is not None


__all__ = [
    "HOOKS_KEY",
    "MARKER",
    "EntrySpec",
    "InstalledHook",
    "MalformedDeliveryConfig",
    "find_all_installed",
    "find_command",
    "find_installed",
    "install_entries",
    "install_entry",
    "is_installed",
    "is_marked",
    "remove_entry",
]
