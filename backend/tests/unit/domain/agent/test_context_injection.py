"""Unit tests for the context-injection descriptor facet (ADR-041).

``ContextInjectionSpec`` is the per-agent record of how Coffer's session context
(rules + memory) reaches the agent's model. Pure value-level logic.
"""

from __future__ import annotations

import pytest

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.context_injection import (
    ContextInjectionSpec,
    HookEvent,
    HookFlavor,
    InjectionMode,
    event_key,
)


def test_hook_event_values_match_claude_external_contract() -> None:
    assert HookEvent.SESSION_START.value == "SessionStart"
    assert HookEvent.SESSION_END.value == "SessionEnd"


def test_injection_modes_cover_the_three_upstream_mechanisms() -> None:
    assert {m.value for m in InjectionMode} == {
        "shell_command",
        "plugin_drop",
        "instructions_block",
    }


@pytest.mark.parametrize(
    ("flavor", "event", "expected"),
    [
        (HookFlavor.CLAUDE, HookEvent.SESSION_START, "SessionStart"),
        (HookFlavor.CLAUDE, HookEvent.SESSION_END, "SessionEnd"),
        (HookFlavor.CURSOR, HookEvent.SESSION_START, "sessionStart"),
        (HookFlavor.CURSOR, HookEvent.SESSION_END, "sessionEnd"),
    ],
)
def test_event_key_spelling_per_flavor(flavor: HookFlavor, event: HookEvent, expected: str) -> None:
    # The same canonical event is spelled differently on disk per agent product.
    assert event_key(flavor, event) == expected


def test_spec_defaults_are_claude_shell_hooks() -> None:
    spec = ContextInjectionSpec(
        mode=InjectionMode.SHELL_COMMAND,
        config_key="settings",
        format=ConfigFileFormat.JSON,
        events=(HookEvent.SESSION_START, HookEvent.SESSION_END),
    )
    assert spec.container_key == "hooks"
    assert spec.flavor is HookFlavor.CLAUDE
    assert spec.config_key == "settings"
    assert spec.format is ConfigFileFormat.JSON
    assert spec.events == (HookEvent.SESSION_START, HookEvent.SESSION_END)


def test_spec_is_frozen_hashable() -> None:
    spec = ContextInjectionSpec(
        mode=InjectionMode.SHELL_COMMAND,
        config_key="hooks",
        format=ConfigFileFormat.JSON,
        events=(HookEvent.SESSION_START,),
        flavor=HookFlavor.CURSOR,
    )
    # frozen dataclass with a tuple field is hashable
    assert hash(spec) == hash(spec)
