"""Unit tests for the hook-install pure text transforms (Slice 6).

``apply_install`` / ``apply_uninstall`` / ``is_installed`` edit the agent's
hooks JSON (Claude ``settings.json`` or Codex ``hooks.json``). They must be
idempotent and must touch ONLY Coffer's own entries (recognised by the command
basename ``coffer-hook``), never user-authored hooks.
"""

from __future__ import annotations

import json

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.hook_injection import HookEvent
from coffer.domain.agent.hook_install import (
    apply_install,
    apply_uninstall,
    is_installed,
)

_CMD = "/opt/coffer/bin/coffer-hook --agent my-claude"
_EVENTS = (HookEvent.SESSION_START, HookEvent.SESSION_END)
_FMT = ConfigFileFormat.JSON


def _hooks(text: str) -> dict:
    return json.loads(text)["hooks"]


def test_install_into_empty_creates_hooks_for_each_event() -> None:
    out = apply_install("", command=_CMD, events=_EVENTS, fmt=_FMT)
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
    once = apply_install("", command=_CMD, events=_EVENTS, fmt=_FMT)
    twice = apply_install(once, command=_CMD, events=_EVENTS, fmt=_FMT)
    assert _hooks(once) == _hooks(twice)
    # exactly one coffer entry per event
    assert len(_hooks(twice)["SessionStart"]) == 1


def test_reinstall_replaces_coffer_entry_with_new_command() -> None:
    once = apply_install("", command=_CMD, events=_EVENTS, fmt=_FMT)
    new_cmd = "/new/path/coffer-hook --agent my-claude"
    out = apply_install(once, command=new_cmd, events=_EVENTS, fmt=_FMT)
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
    out = apply_install(json.dumps(user), command=_CMD, events=_EVENTS, fmt=_FMT)
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
    out = apply_install("", command=_CMD, events=_EVENTS, fmt=_FMT)
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
    installed = apply_install(json.dumps(seeded), command=_CMD, events=_EVENTS, fmt=_FMT)
    out = apply_uninstall(installed, events=_EVENTS, fmt=_FMT)
    data = json.loads(out)
    assert data["other"] == 1
    starts = data["hooks"]["SessionStart"]
    assert starts == [user_entry]
    # SessionEnd had only coffer's entry → array dropped cleanly
    assert "SessionEnd" not in data["hooks"]


def test_uninstall_drops_empty_hooks_object() -> None:
    installed = apply_install("", command=_CMD, events=_EVENTS, fmt=_FMT)
    out = apply_uninstall(installed, events=_EVENTS, fmt=_FMT)
    data = json.loads(out)
    assert "hooks" not in data
    assert is_installed(out, events=_EVENTS, fmt=_FMT) is False


def test_uninstall_on_empty_is_noop() -> None:
    out = apply_uninstall("", events=_EVENTS, fmt=_FMT)
    assert json.loads(out) == {}


def test_install_single_event_only_codex() -> None:
    # Codex installs SessionStart only.
    out = apply_install("", command=_CMD, events=(HookEvent.SESSION_START,), fmt=_FMT)
    hooks = _hooks(out)
    assert set(hooks) == {"SessionStart"}
