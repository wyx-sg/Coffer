"""Validate .claude/settings.json wires every hook script that exists on disk."""

from __future__ import annotations

import json

from .conftest import HOOKS_DIR, REPO_ROOT

SETTINGS = REPO_ROOT / ".claude" / "settings.json"

#: Every hook script `agents/harness.md` documents, keyed by the event + matcher
#: it must be wired on. A script that exists on disk but is not wired here is
#: documentation, not enforcement — which is exactly how `verify_before_commit`
#: went unwired while the harness doc claimed it ran on every commit.
EXPECTED_WIRING: dict[tuple[str, str | None], set[str]] = {
    ("PostToolUse", "Edit|Write"): {"auto_format.py"},
    ("PreToolUse", "Bash"): {"block_dangerous_bash.py", "verify_before_commit.py"},
    ("SessionStart", None): {"session_context.py"},
}


def _load() -> dict:
    return json.loads(SETTINGS.read_text())


def _wired() -> dict[tuple[str, str | None], set[str]]:
    wired: dict[tuple[str, str | None], set[str]] = {}
    for event, groups in _load()["hooks"].items():
        for group in groups:
            key = (event, group.get("matcher"))
            for h in group["hooks"]:
                if h.get("type") == "command":
                    wired.setdefault(key, set()).add(h["command"].rsplit("/", 1)[-1])
    return wired


def test_settings_is_valid_json() -> None:
    assert SETTINGS.exists()
    _load()  # raises if malformed


def test_every_event_is_wired() -> None:
    hooks = _load()["hooks"]
    assert "PostToolUse" in hooks
    assert "PreToolUse" in hooks
    assert "SessionStart" in hooks


def test_each_documented_hook_is_wired_on_its_event() -> None:
    """The four scripts, by name, on the event + matcher harness.md documents."""
    wired = _wired()
    for key, expected in EXPECTED_WIRING.items():
        assert wired.get(key) == expected, (
            f"{key}: expected hooks {sorted(expected)}, settings.json wires "
            f"{sorted(wired.get(key, set()))}"
        )


def test_every_hook_script_on_disk_is_wired() -> None:
    """No orphan scripts: a hook that exists but is not in settings.json never runs."""
    on_disk = {p.name for p in HOOKS_DIR.glob("*.py")}
    wired = set().union(*_wired().values())
    assert on_disk == wired, f"on disk but unwired: {sorted(on_disk - wired)}"


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
