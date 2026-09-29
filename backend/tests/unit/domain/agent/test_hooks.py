"""Parsing an agent's native hook files (spec agent-registry "List every hook
in the agent's native config")."""

from __future__ import annotations

import json

import pytest

from coffer.domain.agent.hooks import HookRow, MalformedHooks, parse_hooks


def test_every_command_hook_becomes_a_row_in_file_order() -> None:
    doc = {
        "env": {"X": "1"},
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume",
                    "hooks": [{"type": "command", "command": "a", "timeout": 10}],
                }
            ],
            "PreToolUse": [
                {"matcher": "", "hooks": [{"type": "command", "command": "b"}]},
                {"hooks": [{"command": "c"}, {"type": "command"}, "junk"]},
            ],
        },
    }
    assert parse_hooks(json.dumps(doc)) == [
        HookRow("SessionStart", "startup|resume", "a", "command", 10),
        HookRow("PreToolUse", None, "b", "command", None),
        HookRow("PreToolUse", None, "c", "command", None),
    ]


@pytest.mark.parametrize("text", ["", "   ", "{}", '{"hooks": []}', '{"hooks": {"Stop": 3}}'])
def test_a_file_without_hooks_yields_none(text: str) -> None:
    assert parse_hooks(text) == []


@pytest.mark.parametrize("text", ["{not json", "[1, 2]"])
def test_a_file_that_is_not_a_json_object_is_refused(text: str) -> None:
    with pytest.raises(MalformedHooks):
        parse_hooks(text)
