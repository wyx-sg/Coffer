"""Unit tests for the hook-injection descriptor facet (Slice 6).

``HookInjectionSpec`` is the per-agent record of how Coffer installs its
``coffer-hook`` SessionStart / SessionEnd hooks. Pure value-level logic.
"""

from __future__ import annotations

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.hook_injection import HookEvent, HookInjectionSpec


def test_hook_event_values_match_external_contract() -> None:
    assert HookEvent.SESSION_START.value == "SessionStart"
    assert HookEvent.SESSION_END.value == "SessionEnd"


def test_spec_container_key_defaults_to_hooks() -> None:
    spec = HookInjectionSpec(
        config_key="settings",
        format=ConfigFileFormat.JSON,
        events=(HookEvent.SESSION_START, HookEvent.SESSION_END),
    )
    assert spec.container_key == "hooks"
    assert spec.config_key == "settings"
    assert spec.format is ConfigFileFormat.JSON
    assert spec.events == (HookEvent.SESSION_START, HookEvent.SESSION_END)


def test_spec_is_frozen_hashable() -> None:
    spec = HookInjectionSpec(
        config_key="hooks",
        format=ConfigFileFormat.JSON,
        events=(HookEvent.SESSION_START,),
    )
    # frozen dataclass with a tuple field is hashable
    assert hash(spec) == hash(spec)
