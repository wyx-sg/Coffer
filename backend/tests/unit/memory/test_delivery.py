"""Unit tests for `coffer.domain.memory.delivery` — the marker, the command
string, and the pure JSON hook-container text transforms.

No filesystem access anywhere here: every fixture is a JSON string built in
the test itself, exactly like `domain/agent/mcp_install.py`'s own tests.
"""

from __future__ import annotations

import json

import pytest

from coffer.domain.memory.delivery import (
    HOOKS_KEY,
    MARKER,
    DeliveryStatus,
    MalformedDeliveryConfig,
    context_invocation,
    find_command,
    hook_command,
    install_entry,
    is_installed,
    remove_entry,
)

# ---------------------------------------------------------------------------
# hook_command / context_invocation
# ---------------------------------------------------------------------------


def test_context_invocation_shells_out_to_coffer_memory_context() -> None:
    assert context_invocation("claude-code") == (
        'coffer memory context --agent claude-code --cwd "$PWD"'
    )


def test_context_invocation_quotes_an_agent_key_with_special_characters() -> None:
    inv = context_invocation("agent with spaces")
    assert "'agent with spaces'" in inv


def test_hook_command_is_marker_prefixed() -> None:
    cmd = hook_command("codex")
    assert cmd.startswith(f": {MARKER};")
    assert context_invocation("codex") in cmd


# ---------------------------------------------------------------------------
# install_entry: fresh config, idempotency, foreign-entry preservation
# ---------------------------------------------------------------------------


def test_install_into_empty_config_adds_one_entry() -> None:
    new_text = install_entry("", event="SessionStart", command="X", matcher="startup")
    data = json.loads(new_text)
    entries = data[HOOKS_KEY]["SessionStart"]
    assert len(entries) == 1
    assert entries[0]["matcher"] == "startup"
    assert entries[0]["hooks"] == [{"type": "command", "command": "X"}]


def test_install_carries_a_timeout_when_given() -> None:
    new_text = install_entry("", event="SessionStart", command="X", matcher=None, timeout=10)
    data = json.loads(new_text)
    leaf = data[HOOKS_KEY]["SessionStart"][0]["hooks"][0]
    assert leaf["timeout"] == 10


def test_install_omits_matcher_when_none() -> None:
    new_text = install_entry("", event="UserPromptSubmit", command="X", matcher=None)
    entry = json.loads(new_text)[HOOKS_KEY]["UserPromptSubmit"][0]
    assert "matcher" not in entry


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
def test_install_is_idempotent_and_installing_twice_leaves_one_entry() -> None:
    once = install_entry("", event="SessionStart", command=hook_command("cc"), matcher="startup")
    twice = install_entry(once, event="SessionStart", command=hook_command("cc"), matcher="startup")
    entries = json.loads(twice)[HOOKS_KEY]["SessionStart"]
    assert len(entries) == 1


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
def test_install_leaves_a_foreign_hook_on_the_same_event_untouched() -> None:
    foreign = {
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": "/usr/local/bin/my-hook.sh"}]}
            ]
        }
    }
    new_text = install_entry(
        json.dumps(foreign), event="SessionStart", command=hook_command("cc"), matcher="startup"
    )
    entries = json.loads(new_text)[HOOKS_KEY]["SessionStart"]
    assert len(entries) == 2
    commands = {e["hooks"][0]["command"] for e in entries}
    assert "/usr/local/bin/my-hook.sh" in commands
    assert hook_command("cc") in commands


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
def test_install_leaves_unrelated_top_level_keys_and_other_events_untouched() -> None:
    skynet_fixture = {
        "env": {},
        "permissions": {"defaultMode": "auto"},
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "/skynet/beforeSubmitPrompt.sh"}]}
            ],
            "Stop": [{"hooks": [{"type": "command", "command": "/skynet/stop.sh"}]}],
        },
        "theme": "dark",
    }
    text = json.dumps(skynet_fixture)
    new_text = install_entry(
        text, event="SessionStart", command=hook_command("cc"), matcher="startup"
    )
    data = json.loads(new_text)
    assert data["env"] == {}
    assert data["permissions"] == {"defaultMode": "auto"}
    assert data["theme"] == "dark"
    assert data[HOOKS_KEY]["UserPromptSubmit"] == skynet_fixture["hooks"]["UserPromptSubmit"]
    assert data[HOOKS_KEY]["Stop"] == skynet_fixture["hooks"]["Stop"]
    assert is_installed(new_text, event="SessionStart")


# ---------------------------------------------------------------------------
# remove_entry
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="memory", scenario="hook installation is marker-scoped and removable")
def test_remove_takes_out_only_coffers_entry_and_preserves_foreign_hooks() -> None:
    fixture = {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "/skynet/beforeSubmitPrompt.sh"}]},
                {"hooks": [{"type": "command", "command": hook_command("codex")}]},
            ],
            "Stop": [{"hooks": [{"type": "command", "command": "/skynet/stop.sh"}]}],
        }
    }
    new_text = remove_entry(json.dumps(fixture), event="UserPromptSubmit")
    data = json.loads(new_text)
    assert data[HOOKS_KEY]["UserPromptSubmit"] == [
        {"hooks": [{"type": "command", "command": "/skynet/beforeSubmitPrompt.sh"}]}
    ]
    assert data[HOOKS_KEY]["Stop"] == fixture["hooks"]["Stop"]
    assert not is_installed(new_text, event="UserPromptSubmit")


def test_remove_drops_a_now_empty_event_array() -> None:
    fixture = {"hooks": {"SessionStart": [{"hooks": [{"command": hook_command("cc")}]}]}}
    new_text = remove_entry(json.dumps(fixture), event="SessionStart")
    data = json.loads(new_text)
    assert "SessionStart" not in data.get(HOOKS_KEY, {})


def test_remove_drops_the_top_level_hooks_key_once_it_is_empty() -> None:
    fixture = {"hooks": {"SessionStart": [{"hooks": [{"command": hook_command("cc")}]}]}}
    new_text = remove_entry(json.dumps(fixture), event="SessionStart")
    assert HOOKS_KEY not in json.loads(new_text)


def test_remove_on_nothing_installed_is_a_clean_no_op() -> None:
    fixture = {"hooks": {"Stop": [{"hooks": [{"command": "/skynet/stop.sh"}]}]}}
    new_text = remove_entry(json.dumps(fixture), event="SessionStart")
    assert json.loads(new_text) == fixture


def test_remove_on_empty_text_does_not_raise() -> None:
    assert json.loads(remove_entry("", event="SessionStart")) == {}


# ---------------------------------------------------------------------------
# find_command / is_installed
# ---------------------------------------------------------------------------


def test_find_command_returns_none_when_absent() -> None:
    assert find_command("", event="SessionStart") is None
    assert not is_installed("", event="SessionStart")


def test_find_command_returns_the_installed_command() -> None:
    text = install_entry("", event="SessionStart", command=hook_command("cc"), matcher="startup")
    assert find_command(text, event="SessionStart") == hook_command("cc")
    assert is_installed(text, event="SessionStart")


# ---------------------------------------------------------------------------
# Malformed config fails loudly
# ---------------------------------------------------------------------------


def test_malformed_json_raises_instead_of_clobbering() -> None:
    with pytest.raises(MalformedDeliveryConfig):
        install_entry("{not json", event="SessionStart", command="X", matcher=None)


def test_non_object_json_raises() -> None:
    with pytest.raises(MalformedDeliveryConfig):
        find_command("[1, 2, 3]", event="SessionStart")


# ---------------------------------------------------------------------------
# DeliveryStatus is a plain, comparable value
# ---------------------------------------------------------------------------


def test_delivery_status_is_frozen_and_comparable() -> None:
    a = DeliveryStatus(agent="cc", installed=True, command="X", event="SessionStart")
    b = DeliveryStatus(agent="cc", installed=True, command="X", event="SessionStart")
    assert a == b
    with pytest.raises(AttributeError):
        a.installed = False  # type: ignore[misc]
