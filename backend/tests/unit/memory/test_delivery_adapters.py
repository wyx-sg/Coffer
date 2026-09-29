"""Unit tests for the per-agent adapters under
`coffer.infrastructure.memory.delivery` — which event/config-key each picks,
the CLI path and output format each command carries, and, for Codex, the trust
hash it computes the way Codex does. No filesystem access: everything is a
string built in the test, same as the domain-level tests.
"""

from __future__ import annotations

import json

import pytest

from coffer.domain.hook_trust import HookTrust
from coffer.domain.memory.delivery import HOOKS_KEY, MARKER, InstalledHook, context_invocation
from coffer.infrastructure.memory.delivery import (
    CLAUDE_CODE_ADAPTER,
    CODEX_ADAPTER,
    delivery_adapters,
)
from coffer.infrastructure.memory.delivery.claude_code import ADAPTER as _CC
from coffer.infrastructure.memory.delivery.codex import ADAPTER as _CODEX
from coffer.infrastructure.memory.delivery.codex import current_hash, trust_key


def test_claude_code_adapter_uses_session_start_and_settings_key() -> None:
    assert CLAUDE_CODE_ADAPTER is _CC
    assert _CC.event == "SessionStart"
    assert _CC.config_key == "settings"


def test_codex_adapter_uses_session_start_and_hooks_key() -> None:
    assert CODEX_ADAPTER is _CODEX
    assert _CODEX.event == "SessionStart"
    assert _CODEX.config_key == "hooks"
    assert _CODEX.trust_config_key == "config"


def test_codex_command_asks_for_session_start_json_and_has_no_ppid_guard() -> None:
    """SessionStart fires once per session, so no guard; and a `$PPID` guard
    would be wrong anyway — every session of one `codex app-server` (Desktop,
    IDE hosts) shares that parent pid."""
    cmd = _CODEX.command_for("cx")
    assert cmd == f": {MARKER}; {context_invocation('cx', hook_event='SessionStart')}"
    assert cmd.endswith("--hook-event SessionStart")
    assert "$PPID" not in cmd
    assert "[ -e" not in cmd


def test_codex_install_matches_every_session_start_source() -> None:
    entry = json.loads(_CODEX.install("", "cx"))[HOOKS_KEY]["SessionStart"][0]
    assert entry["matcher"] == "startup|resume|clear|compact"
    assert entry["hooks"][0]["timeout"] == 10


@pytest.mark.parametrize("adapter", delivery_adapters("/Users/me/.coffer/bin/coffer"))
def test_every_adapter_runs_the_cli_by_the_absolute_path_it_was_given(adapter: object) -> None:
    """A hook runs under a shell that need not have `~/.coffer/bin` on its
    PATH (Codex's `/bin/zsh`, Claude Code started from the Dock)."""
    cmd = adapter.command_for("u1")  # type: ignore[attr-defined]
    assert cmd.startswith(f": {MARKER}; /Users/me/.coffer/bin/coffer memory context ")
    assert adapter.is_coffer_command(cmd)  # type: ignore[attr-defined]


def test_a_cli_path_with_a_space_is_quoted() -> None:
    (cc, _cx) = delivery_adapters("/Users/a b/.coffer/bin/coffer")
    assert "'/Users/a b/.coffer/bin/coffer' memory context" in cc.command_for("u1")


def test_codex_install_moves_an_older_builds_user_prompt_submit_hook() -> None:
    """The migration: an older build's guarded entry on UserPromptSubmit is
    replaced by one on SessionStart; foreign hooks on both events stay."""
    legacy = f': {MARKER}; f="$TMPDIR/x-$PPID"; [ -e "$f" ] || {{ coffer memory context; }}'
    foreign = {"hooks": [{"type": "command", "command": "/skynet/beforeSubmitPrompt.sh"}]}
    orca = {"hooks": [{"type": "command", "command": "/orca/session.sh"}]}
    text = json.dumps(
        {
            "hooks": {
                "UserPromptSubmit": [foreign, {"hooks": [{"type": "command", "command": legacy}]}],
                "SessionStart": [orca],
            }
        }
    )
    found = _CODEX.find(text)
    assert found is not None and found.event == "UserPromptSubmit"

    data = json.loads(_CODEX.install(text, "cx"))
    assert data[HOOKS_KEY]["UserPromptSubmit"] == [foreign]
    assert data[HOOKS_KEY]["SessionStart"][0] == orca
    assert data[HOOKS_KEY]["SessionStart"][1]["hooks"][0]["command"] == _CODEX.command_for("cx")


def test_codex_remove_takes_out_an_older_builds_entry_too() -> None:
    legacy = {"hooks": [{"type": "command", "command": f": {MARKER}; coffer memory context"}]}
    text = json.dumps({"hooks": {"UserPromptSubmit": [legacy]}})
    assert json.loads(_CODEX.remove(text)) == {}


def test_codex_install_coexists_with_a_foreign_session_start_entry() -> None:
    skynet_fixture = {
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": "/skynet/session.sh", "timeout": 15}]}
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
    entries = data[HOOKS_KEY]["SessionStart"]
    assert len(entries) == 2
    assert entries[0] == skynet_fixture["hooks"]["SessionStart"][0]
    assert data[HOOKS_KEY]["PreToolUse"] == skynet_fixture["hooks"]["PreToolUse"]
    assert data[HOOKS_KEY]["Stop"] == skynet_fixture["hooks"]["Stop"]

    removed = json.loads(_CODEX.remove(new_text))
    assert removed == skynet_fixture


# --- Codex's trust hash ------------------------------------------------------
#
# The expected values are what Codex 0.155.1's own `hooks/list` app-server RPC
# reported as `currentHash` for these exact definitions.


def test_codex_hash_matches_codex_for_a_session_start_hook_with_a_matcher() -> None:
    command = (
        ": coffer-memory; /Users/x/.coffer/bin/coffer memory context --agent-uid 01ABC "
        '--cwd "$PWD" --hook-event SessionStart'
    )
    hook = InstalledHook(
        event="SessionStart",
        command=command,
        matcher="startup|resume|clear|compact",
        group_index=1,
        handler_index=0,
        handler={"type": "command", "command": command, "timeout": 10},
    )
    assert current_hash(hook) == (
        "sha256:906fd8bc9dc1be5e4daef2ad0b0a898521c98deb7ac098e9518de8ff5bfe8766"
    )
    assert trust_key("/h/.codex/hooks.json", hook) == "/h/.codex/hooks.json:session_start:1:0"


def test_codex_hash_matches_codex_with_its_default_timeout() -> None:
    hook = InstalledHook(
        event="SessionStart",
        command="echo other",
        matcher=None,
        group_index=0,
        handler_index=0,
        handler={"type": "command", "command": "echo other"},
    )
    assert current_hash(hook) == (
        "sha256:be3e1d16a063ea554d2caec93d324c639ce24dd8d145e71c13581c5a0e6b0a32"
    )


def _approved(key: str, digest: str, *, enabled: bool | None = None) -> str:
    extra = "" if enabled is None else f"enabled = {str(enabled).lower()}\n"
    return f'model = "x"\n\n[hooks.state."{key}"]\n{extra}trusted_hash = "{digest}"\n'


def test_codex_trust_reads_every_state_codex_can_record() -> None:
    path = "/h/.codex/hooks.json"
    text = _CODEX.install("", "cx")
    hook = _CODEX.find(text)
    assert hook is not None
    key = trust_key(path, hook)
    digest = current_hash(hook)

    assert _CODEX.trust(text, None, path) is HookTrust.UNTRUSTED
    assert _CODEX.trust(text, 'model = "x"\n', path) is HookTrust.UNTRUSTED
    assert _CODEX.trust(text, _approved(key, digest), path) is HookTrust.TRUSTED
    assert _CODEX.trust(text, _approved(key, "sha256:old"), path) is HookTrust.MODIFIED
    assert _CODEX.trust(text, _approved(key, digest, enabled=False), path) is (HookTrust.DISABLED)
    assert _CODEX.trust(text, "not = [toml", path) is HookTrust.UNKNOWN
    # Trust is per slot: approval recorded for another position does not count.
    assert _CODEX.trust(text, _approved(key.replace(":0:0", ":1:0"), digest), path) is (
        HookTrust.UNTRUSTED
    )
