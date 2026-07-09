"""Unit tests for the hook-install pure text transforms (ADR-042).

``apply_install`` / ``apply_uninstall`` / ``is_installed`` edit the agent's hooks
JSON in one of two flavors: matcher groups with PascalCase event keys (Claude
``settings.json``, Codex ``hooks.json``) or flat command entries with camelCase
keys and a top-level ``version`` (Cursor ``hooks.json``). They must be idempotent
and must touch ONLY Coffer's own entries (recognised by the command basename
``coffer-hook``), never user-authored hooks.
"""

from __future__ import annotations

import json

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.context_injection import HookEvent, HookFlavor
from coffer.domain.agent.hook_install import (
    apply_install,
    apply_uninstall,
    is_installed,
)

_CMD = "/opt/coffer/bin/coffer-hook --agent my-claude"
_EVENTS = (HookEvent.SESSION_START, HookEvent.SESSION_END)
_FMT = ConfigFileFormat.JSON
_CMDS = dict.fromkeys(_EVENTS, _CMD)


def _hooks(text: str) -> dict:
    return json.loads(text)["hooks"]


def test_install_into_empty_creates_hooks_for_each_event() -> None:
    out = apply_install("", commands=_CMDS, events=_EVENTS, fmt=_FMT)
    hooks = _hooks(out)
    assert set(hooks) == {"SessionStart", "SessionEnd"}
    start = hooks["SessionStart"]
    assert start == [
        {
            "matcher": "startup|resume|clear|compact",
            "hooks": [{"type": "command", "command": _CMD}],
        }
    ]
    end = hooks["SessionEnd"]
    assert end[0]["matcher"] == "clear|logout|prompt_input_exit|other"
    assert end[0]["hooks"][0]["command"] == _CMD


def test_install_is_idempotent() -> None:
    once = apply_install("", commands=_CMDS, events=_EVENTS, fmt=_FMT)
    twice = apply_install(once, commands=_CMDS, events=_EVENTS, fmt=_FMT)
    assert _hooks(once) == _hooks(twice)
    # exactly one coffer entry per event
    assert len(_hooks(twice)["SessionStart"]) == 1


def test_reinstall_replaces_coffer_entry_with_new_command() -> None:
    once = apply_install("", commands=_CMDS, events=_EVENTS, fmt=_FMT)
    new_cmd = "/new/path/coffer-hook --agent my-claude"
    out = apply_install(once, commands=dict.fromkeys(_EVENTS, new_cmd), events=_EVENTS, fmt=_FMT)
    starts = _hooks(out)["SessionStart"]
    assert len(starts) == 1
    assert starts[0]["hooks"][0]["command"] == new_cmd


def test_install_preserves_user_hooks_for_same_event() -> None:
    user = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup",
                    "hooks": [{"type": "command", "command": "/usr/local/bin/my-own-hook"}],
                }
            ]
        },
        "model": "claude-opus-4",
    }
    out = apply_install(json.dumps(user), commands=_CMDS, events=_EVENTS, fmt=_FMT)
    data = json.loads(out)
    # unrelated top-level key preserved
    assert data["model"] == "claude-opus-4"
    starts = data["hooks"]["SessionStart"]
    commands = [h["hooks"][0]["command"] for h in starts]
    assert "/usr/local/bin/my-own-hook" in commands
    assert _CMD in commands
    assert len(starts) == 2


def test_is_installed_true_after_install_false_on_empty() -> None:
    assert is_installed("", events=_EVENTS, fmt=_FMT) is False
    out = apply_install("", commands=_CMDS, events=_EVENTS, fmt=_FMT)
    assert is_installed(out, events=_EVENTS, fmt=_FMT) is True


def test_is_installed_false_when_only_user_hooks_present() -> None:
    user = {
        "hooks": {
            "SessionStart": [
                {"matcher": "startup", "hooks": [{"type": "command", "command": "/bin/other"}]}
            ]
        }
    }
    assert is_installed(json.dumps(user), events=_EVENTS, fmt=_FMT) is False


def test_uninstall_removes_only_coffer_entries() -> None:
    user_entry = {
        "matcher": "startup",
        "hooks": [{"type": "command", "command": "/usr/local/bin/my-own-hook"}],
    }
    seeded = {"hooks": {"SessionStart": [user_entry]}, "other": 1}
    installed = apply_install(json.dumps(seeded), commands=_CMDS, events=_EVENTS, fmt=_FMT)
    out = apply_uninstall(installed, events=_EVENTS, fmt=_FMT)
    data = json.loads(out)
    assert data["other"] == 1
    starts = data["hooks"]["SessionStart"]
    assert starts == [user_entry]
    # SessionEnd had only coffer's entry → array dropped cleanly
    assert "SessionEnd" not in data["hooks"]


def test_uninstall_drops_empty_hooks_object() -> None:
    installed = apply_install("", commands=_CMDS, events=_EVENTS, fmt=_FMT)
    out = apply_uninstall(installed, events=_EVENTS, fmt=_FMT)
    data = json.loads(out)
    assert "hooks" not in data
    assert is_installed(out, events=_EVENTS, fmt=_FMT) is False


def test_uninstall_on_empty_is_noop() -> None:
    out = apply_uninstall("", events=_EVENTS, fmt=_FMT)
    assert json.loads(out) == {}


def test_install_single_event_only_codex() -> None:
    # Codex installs SessionStart only.
    out = apply_install(
        "", commands={HookEvent.SESSION_START: _CMD}, events=(HookEvent.SESSION_START,), fmt=_FMT
    )
    hooks = _hooks(out)
    assert set(hooks) == {"SessionStart"}


# --- cursor flavor (ADR-042) ---------------------------------------------------

_CURSOR_CMD = "/opt/coffer/bin/coffer-hook --agent my-cursor --dialect cursor --event sessionStart"
_CURSOR_EVENTS = (HookEvent.SESSION_START,)
_CURSOR_CMDS = {HookEvent.SESSION_START: _CURSOR_CMD}


def _install_cursor(text: str = "") -> str:
    return apply_install(
        text,
        commands=_CURSOR_CMDS,
        events=_CURSOR_EVENTS,
        fmt=_FMT,
        flavor=HookFlavor.CURSOR,
    )


def test_cursor_install_uses_flat_entries_camelcase_key_and_version() -> None:
    data = json.loads(_install_cursor())
    assert data["version"] == 1
    # Flat command entry — no matcher, no nested "hooks" list.
    assert data["hooks"] == {"sessionStart": [{"command": _CURSOR_CMD}]}


def test_cursor_install_preserves_existing_version_and_user_hooks() -> None:
    seeded = {
        "version": 2,
        "hooks": {
            "sessionStart": [{"command": "/usr/local/bin/skynet_sessionStart.sh"}],
            "beforeSubmitPrompt": [{"command": "/usr/local/bin/skynet_submit.sh"}],
        },
    }
    data = json.loads(_install_cursor(json.dumps(seeded)))
    # A newer/user-set schema version is never rewritten.
    assert data["version"] == 2
    # Unrelated event untouched.
    assert data["hooks"]["beforeSubmitPrompt"] == [{"command": "/usr/local/bin/skynet_submit.sh"}]
    commands = [e["command"] for e in data["hooks"]["sessionStart"]]
    assert commands == ["/usr/local/bin/skynet_sessionStart.sh", _CURSOR_CMD]


def test_cursor_install_is_idempotent() -> None:
    once = _install_cursor()
    twice = _install_cursor(once)
    assert json.loads(once) == json.loads(twice)
    assert len(json.loads(twice)["hooks"]["sessionStart"]) == 1


def test_cursor_is_installed_roundtrip_and_flavor_isolation() -> None:
    out = _install_cursor()
    assert is_installed(out, events=_CURSOR_EVENTS, fmt=_FMT, flavor=HookFlavor.CURSOR) is True
    # The claude flavor looks for "SessionStart" + matcher groups → not found.
    assert is_installed(out, events=_CURSOR_EVENTS, fmt=_FMT, flavor=HookFlavor.CLAUDE) is False


def test_cursor_uninstall_removes_only_coffer_entry_and_keeps_version() -> None:
    user = {"command": "/usr/local/bin/skynet_sessionStart.sh"}
    seeded = {"version": 1, "hooks": {"sessionStart": [user]}}
    installed = _install_cursor(json.dumps(seeded))
    out = apply_uninstall(installed, events=_CURSOR_EVENTS, fmt=_FMT, flavor=HookFlavor.CURSOR)
    data = json.loads(out)
    assert data["hooks"]["sessionStart"] == [user]
    # `version` describes the file, not our entry — it survives uninstall.
    assert data["version"] == 1
    assert is_installed(out, events=_CURSOR_EVENTS, fmt=_FMT, flavor=HookFlavor.CURSOR) is False


def test_cursor_uninstall_drops_empty_hooks_object() -> None:
    out = apply_uninstall(
        _install_cursor(), events=_CURSOR_EVENTS, fmt=_FMT, flavor=HookFlavor.CURSOR
    )
    assert "hooks" not in json.loads(out)


# --- review hardening (ADR-042 follow-up) --------------------------------------


def test_malformed_user_command_does_not_raise() -> None:
    """A user hook with an unbalanced quote must not crash install/status.

    This runs in the daemon, outside coffer-hook's failure-is-silent wrapper — a
    raise here 500s the API for a file that merely contains someone else's quoting.
    """
    seeded = {"version": 1, "hooks": {"sessionStart": [{"command": 'echo "unclosed'}]}}
    text = json.dumps(seeded)

    assert is_installed(text, events=_CURSOR_EVENTS, fmt=_FMT, flavor=HookFlavor.CURSOR) is False
    out = _install_cursor(text)
    # The malformed user entry survives untouched next to ours.
    entries = json.loads(out)["hooks"]["sessionStart"]
    assert {"command": 'echo "unclosed'} in entries
    assert {"command": _CURSOR_CMD} in entries

    restored = apply_uninstall(out, events=_CURSOR_EVENTS, fmt=_FMT, flavor=HookFlavor.CURSOR)
    assert json.loads(restored)["hooks"]["sessionStart"] == [{"command": 'echo "unclosed'}]


def test_malformed_command_in_claude_matcher_group_does_not_raise() -> None:
    seeded = {"hooks": {"SessionStart": [{"matcher": "startup", "hooks": [{"command": "'oops"}]}]}}
    assert is_installed(json.dumps(seeded), events=_EVENTS, fmt=_FMT) is False


def test_uninstall_removes_version_coffer_added_to_an_empty_file() -> None:
    # install into a file with no `version` writes one; uninstall must undo it,
    # or uninstall does not undo install.
    out = apply_uninstall(
        _install_cursor(""), events=_CURSOR_EVENTS, fmt=_FMT, flavor=HookFlavor.CURSOR
    )
    assert json.loads(out) == {}


def test_uninstall_keeps_version_when_other_content_remains() -> None:
    seeded = {"version": 3, "hooks": {"beforeSubmitPrompt": [{"command": "/x/other.sh"}]}}
    out = apply_uninstall(
        _install_cursor(json.dumps(seeded)),
        events=_CURSOR_EVENTS,
        fmt=_FMT,
        flavor=HookFlavor.CURSOR,
    )
    data = json.loads(out)
    # `version` describes the file, and the file still has the user's content.
    assert data["version"] == 3
    assert data["hooks"]["beforeSubmitPrompt"] == [{"command": "/x/other.sh"}]
