"""Descriptor hook + native-memory facets (Slice 6).

Claude Code installs SessionStart + SessionEnd into ``settings`` (JSON); Codex
installs SessionStart only into ``hooks`` (JSON) — it has no session-end event.
The native-memory-disable facet records which file+format holds the toggle.
"""

from __future__ import annotations

from coffer.domain.agent.config_files import ConfigFileFormat, spec_for
from coffer.domain.agent.descriptor import descriptor_for, native_memory_disable_target
from coffer.domain.agent.hook_injection import HookEvent
from coffer.domain.agent.types import AgentType


def test_claude_code_hooks_spec() -> None:
    d = descriptor_for(AgentType.CLAUDE_CODE)
    assert d.hooks is not None
    assert d.hooks.config_key == "settings"
    assert d.hooks.format is ConfigFileFormat.JSON
    assert d.hooks.events == (HookEvent.SESSION_START, HookEvent.SESSION_END)
    assert d.hooks.container_key == "hooks"


def test_codex_hooks_spec_session_start_only() -> None:
    d = descriptor_for(AgentType.CODEX)
    assert d.hooks is not None
    assert d.hooks.config_key == "hooks"
    assert d.hooks.format is ConfigFileFormat.JSON
    assert d.hooks.events == (HookEvent.SESSION_START,)


def test_hook_config_keys_are_allowlisted() -> None:
    # The descriptor's hook config_key must resolve in the file allowlist.
    for at in (AgentType.CLAUDE_CODE, AgentType.CODEX):
        d = descriptor_for(at)
        assert d.hooks is not None
        spec = spec_for(at, d.hooks.config_key)
        assert spec.format is ConfigFileFormat.JSON


def test_native_memory_disable_target_per_type() -> None:
    claude_key, claude_fmt = native_memory_disable_target(AgentType.CLAUDE_CODE)
    assert claude_key == "settings"
    assert claude_fmt is ConfigFileFormat.JSON

    codex_key, codex_fmt = native_memory_disable_target(AgentType.CODEX)
    assert codex_key == "config"
    assert codex_fmt is ConfigFileFormat.TOML
