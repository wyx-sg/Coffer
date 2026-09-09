"""The collapsed context-injection facet: one shell hook, no mode/flavor axes."""

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.context_injection import (
    HOOK_CONTAINER_KEY,
    ContextInjectionSpec,
    HookEvent,
)


def test_spec_carries_only_the_shell_hook_fields():
    spec = ContextInjectionSpec(
        config_key="settings",
        format=ConfigFileFormat.JSON,
        events=(HookEvent.SESSION_START, HookEvent.SESSION_END),
    )
    assert spec.config_key == "settings"
    assert spec.events == (HookEvent.SESSION_START, HookEvent.SESSION_END)
    assert not hasattr(spec, "mode")
    assert not hasattr(spec, "flavor")
    assert not hasattr(spec, "plugin_flavor")


def test_hook_container_key_is_hooks():
    assert HOOK_CONTAINER_KEY == "hooks"


def test_event_values_are_the_on_disk_keys():
    assert HookEvent.SESSION_START.value == "SessionStart"
    assert HookEvent.SESSION_END.value == "SessionEnd"
