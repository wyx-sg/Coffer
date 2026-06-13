"""Validate .claude/settings.json wires every hook script that exists on disk."""

from __future__ import annotations

import json

from .conftest import HOOKS_DIR, REPO_ROOT

SETTINGS = REPO_ROOT / ".claude" / "settings.json"


def _load() -> dict:
    return json.loads(SETTINGS.read_text())


def test_settings_is_valid_json() -> None:
    assert SETTINGS.exists()
    _load()  # raises if malformed


def test_every_event_is_wired() -> None:
    hooks = _load()["hooks"]
    assert "PostToolUse" in hooks
    assert "PreToolUse" in hooks
    assert "SessionStart" in hooks


def test_referenced_hook_scripts_exist() -> None:
    data = _load()
    referenced = []
    for groups in data["hooks"].values():
        for group in groups:
            for h in group["hooks"]:
                if h.get("type") == "command":
                    referenced.append(h["command"])
    assert referenced, "no command hooks wired"
    for cmd in referenced:
        name = cmd.rsplit("/", 1)[-1]
        assert (HOOKS_DIR / name).exists(), f"settings.json references missing hook: {name}"


def test_permissions_present() -> None:
    perms = _load()["permissions"]
    assert isinstance(perms.get("allow"), list) and perms["allow"]
    assert isinstance(perms.get("deny"), list) and perms["deny"]
