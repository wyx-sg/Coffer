"""Unit tests for the per-agent adapters under
`coffer.infrastructure.memory.delivery` — which event/config-key each picks,
and, for Codex, the shape of the once-per-session guard around the bare
invocation. No filesystem access: everything is a JSON string built in the
test, same as the domain-level tests.
"""

from __future__ import annotations

import json

from coffer.domain.memory.delivery import HOOKS_KEY, MARKER, context_invocation
from coffer.infrastructure.memory.delivery import CLAUDE_CODE_ADAPTER, CODEX_ADAPTER
from coffer.infrastructure.memory.delivery.claude_code import ADAPTER as _CC
from coffer.infrastructure.memory.delivery.codex import ADAPTER as _CODEX


def test_claude_code_adapter_uses_session_start_and_settings_key() -> None:
    assert CLAUDE_CODE_ADAPTER is _CC
    assert _CC.event == "SessionStart"
    assert _CC.config_key == "settings"


def test_codex_adapter_uses_user_prompt_submit_and_hooks_key() -> None:
    assert CODEX_ADAPTER is _CODEX
    assert _CODEX.event == "UserPromptSubmit"
    assert _CODEX.config_key == "hooks"


def test_claude_code_matcher_covers_every_session_start_source() -> None:
    new_text = _CC.install("", "cc")
    entry = json.loads(new_text)[HOOKS_KEY]["SessionStart"][0]
    for source in ("startup", "resume", "clear", "compact"):
        assert source in entry["matcher"]


def test_claude_code_command_carries_no_guard() -> None:
    cmd = _CC.command_for("cc")
    assert cmd == f": {MARKER}; {context_invocation('cc')}"


def test_codex_command_is_marker_prefixed_and_guarded_by_ppid_lockfile() -> None:
    cmd = _CODEX.command_for("codex")
    assert cmd.startswith(f": {MARKER};")
    assert "$PPID" in cmd
    assert '[ -e "$f" ]' in cmd
    assert context_invocation("codex") in cmd


def test_codex_and_claude_code_commands_share_the_same_marker_prefix() -> None:
    assert _CC.command_for("cc").startswith(f": {MARKER}")
    assert _CODEX.command_for("codex").startswith(f": {MARKER}")


def test_codex_install_has_no_matcher_field() -> None:
    new_text = _CODEX.install("", "codex")
    entry = json.loads(new_text)[HOOKS_KEY]["UserPromptSubmit"][0]
    assert "matcher" not in entry


def test_codex_install_coexists_with_a_foreign_user_prompt_submit_entry() -> None:
    skynet_fixture = {
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "/bin/bash /skynet/beforeSubmitPrompt.sh",
                            "timeout": 15,
                        }
                    ]
                }
            ],
            "PreToolUse": [
                {
                    "matcher": "mcp__.*",
                    "hooks": [{"type": "command", "command": "/skynet/beforeMCP.sh"}],
                }
            ],
            "Stop": [{"hooks": [{"type": "command", "command": "/skynet/stop.sh"}]}],
        }
    }
    new_text = _CODEX.install(json.dumps(skynet_fixture), "codex")
    data = json.loads(new_text)
    ups_entries = data[HOOKS_KEY]["UserPromptSubmit"]
    assert len(ups_entries) == 2
    commands = {e["hooks"][0]["command"] for e in ups_entries}
    assert "/bin/bash /skynet/beforeSubmitPrompt.sh" in commands
    assert _CODEX.find_command(new_text) in commands
    # Untouched entirely.
    assert data[HOOKS_KEY]["PreToolUse"] == skynet_fixture["hooks"]["PreToolUse"]
    assert data[HOOKS_KEY]["Stop"] == skynet_fixture["hooks"]["Stop"]

    removed = _CODEX.remove(new_text)
    removed_data = json.loads(removed)
    assert (
        removed_data[HOOKS_KEY]["UserPromptSubmit"] == skynet_fixture["hooks"]["UserPromptSubmit"]
    )
    assert removed_data[HOOKS_KEY]["PreToolUse"] == skynet_fixture["hooks"]["PreToolUse"]
    assert removed_data[HOOKS_KEY]["Stop"] == skynet_fixture["hooks"]["Stop"]
