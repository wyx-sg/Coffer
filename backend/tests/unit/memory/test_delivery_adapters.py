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
from coffer.domain.memory.delivery import (
    DELIVERY_EVENTS,
    HOOKS_KEY,
    MARKER,
    InstalledHook,
    events_label,
    hook_invocation,
)
from coffer.infrastructure.memory.delivery import (
    CLAUDE_CODE_ADAPTER,
    CODEX_ADAPTER,
    delivery_adapters,
)
from coffer.infrastructure.memory.delivery.claude_code import ADAPTER as _CC
from coffer.infrastructure.memory.delivery.codex import ADAPTER as _CODEX
from coffer.infrastructure.memory.delivery.codex import current_hash, trust_key

_ALL_EVENTS = "PostToolUse,PreToolUse,SessionStart,UserPromptSubmit"


def test_claude_code_adapter_uses_session_start_and_settings_key() -> None:
    assert CLAUDE_CODE_ADAPTER is _CC
    assert _CC.event == _ALL_EVENTS == events_label(DELIVERY_EVENTS)
    assert _CC.config_key == "settings"


def test_codex_adapter_uses_session_start_and_hooks_key() -> None:
    assert CODEX_ADAPTER is _CODEX
    assert _CODEX.event == _ALL_EVENTS
    assert _CODEX.config_key == "hooks"
    assert _CODEX.trust_config_key == "config"


def test_codex_command_asks_for_session_start_json_and_has_no_ppid_guard() -> None:
    """One command on every event: it reads the event from stdin, so it
    carries no `--hook-event`; and no `$PPID` guard — every session of one
    `codex app-server` (Desktop, IDE hosts) shares that parent pid."""
    cmd = _CODEX.command_for("cx")
    assert cmd == f": {MARKER}; {hook_invocation('cx')}"
    assert " memory hook " in cmd
    assert "--hook-event" not in cmd
    assert "$PPID" not in cmd
    assert "[ -e" not in cmd


def test_codex_install_matches_every_session_start_source() -> None:
    hooks = json.loads(_CODEX.install("", "cx"))[HOOKS_KEY]
    entry = hooks["SessionStart"][0]
    assert entry["matcher"] == "startup|resume|clear|compact"
    assert entry["hooks"][0]["timeout"] == 10
    assert "matcher" not in hooks["UserPromptSubmit"][0]
    assert hooks["UserPromptSubmit"][0]["hooks"][0]["timeout"] == 5
    for event in ("PreToolUse", "PostToolUse"):
        assert hooks[event][0]["matcher"] == "Bash"
        assert hooks[event][0]["hooks"][0]["timeout"] == 5


@pytest.mark.parametrize("adapter", [_CC, _CODEX])
def test_every_adapter_installs_the_same_command_on_all_four_events(adapter: object) -> None:
    text = adapter.install("", "u1")  # type: ignore[attr-defined]
    hooks = json.loads(text)[HOOKS_KEY]
    assert set(hooks) == set(DELIVERY_EVENTS)
    cmd = adapter.command_for("u1")  # type: ignore[attr-defined]
    for event in DELIVERY_EVENTS:
        assert [e["hooks"][0]["command"] for e in hooks[event]] == [cmd]
    found = adapter.find_all(text)  # type: ignore[attr-defined]
    assert sorted(h.event for h in found) == sorted(DELIVERY_EVENTS)
    assert adapter.install(text, "u1") == text  # type: ignore[attr-defined]


@pytest.mark.parametrize("adapter", delivery_adapters("/Users/me/.coffer/bin/coffer"))
def test_every_adapter_runs_the_cli_by_the_absolute_path_it_was_given(adapter: object) -> None:
    """A hook runs under a shell that need not have `~/.coffer/bin` on its
    PATH (Codex's `/bin/zsh`, Claude Code started from the Dock)."""
    cmd = adapter.command_for("u1")  # type: ignore[attr-defined]
    assert cmd.startswith(f": {MARKER}; /Users/me/.coffer/bin/coffer memory hook ")
    assert adapter.is_coffer_command(cmd)  # type: ignore[attr-defined]


def test_a_cli_path_with_a_space_is_quoted() -> None:
    (cc, _cx) = delivery_adapters("/Users/a b/.coffer/bin/coffer")
    assert "'/Users/a b/.coffer/bin/coffer' memory hook" in cc.command_for("u1")


def test_codex_install_moves_an_older_builds_user_prompt_submit_hook() -> None:
    """The migration: an older build's guarded entry on UserPromptSubmit is
    replaced by this build's entries; foreign hooks on both events stay first."""
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
    ups = data[HOOKS_KEY]["UserPromptSubmit"]
    assert len(ups) == 2
    assert ups[0] == foreign
    assert ups[1]["hooks"][0]["command"] == _CODEX.command_for("cx")
    assert legacy not in json.dumps(data)
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
    pre = data[HOOKS_KEY]["PreToolUse"]
    assert len(pre) == 2
    assert pre[0] == skynet_fixture["hooks"]["PreToolUse"][0]
    assert pre[1]["matcher"] == "Bash"
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
    hooks = _CODEX.find_all(text)
    assert len(hooks) == 4
    first, rest = hooks[0], hooks[1:]
    key = trust_key(path, first)
    digest = current_hash(first)
    # Every other entry approved as it stands; only the first one varies.
    others = "".join(
        f'\n[hooks.state."{trust_key(path, h)}"]\ntrusted_hash = "{current_hash(h)}"\n'
        for h in rest
    )

    def with_others(first_state: str) -> str:
        return first_state + others

    assert _CODEX.trust(text, None, path) is HookTrust.UNTRUSTED
    assert _CODEX.trust(text, 'model = "x"\n', path) is HookTrust.UNTRUSTED
    assert _CODEX.trust(text, with_others(_approved(key, digest)), path) is HookTrust.TRUSTED
    assert _CODEX.trust(text, with_others(_approved(key, "sha256:old")), path) is (
        HookTrust.MODIFIED
    )
    assert _CODEX.trust(text, with_others(_approved(key, digest, enabled=False)), path) is (
        HookTrust.DISABLED
    )
    assert _CODEX.trust(text, "not = [toml", path) is HookTrust.UNKNOWN
    # Trust is per slot: approval recorded for another position does not count.
    assert _CODEX.trust(
        text, with_others(_approved(key.replace(":0:0", ":1:0"), digest)), path
    ) is (HookTrust.UNTRUSTED)
    # Four entries are four approvals: one approved alone is not enough.
    assert _CODEX.trust(text, _approved(key, digest), path) is HookTrust.UNTRUSTED
