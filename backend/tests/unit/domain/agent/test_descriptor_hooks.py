"""Descriptor context-injection + native-memory facets.

Claude Code installs SessionStart + SessionEnd into ``settings`` (JSON); Codex
installs SessionStart only — it has no usable session-end event. Both use the
one shell-hook mechanism (FR-043). The native-memory-disable facet records which
file+format holds the toggle.
"""

from __future__ import annotations

from coffer.domain.agent.config_files import ConfigFileFormat, spec_for
from coffer.domain.agent.context_injection import HookEvent
from coffer.domain.agent.descriptor import descriptor_for, native_memory_disable_target
from coffer.domain.agent.types import AgentType


def test_claude_code_injection_spec() -> None:
    d = descriptor_for(AgentType.CLAUDE_CODE)
    assert d.context_injection is not None
    assert d.context_injection.config_key == "settings"
    assert d.context_injection.format is ConfigFileFormat.JSON
    assert d.context_injection.events == (HookEvent.SESSION_START, HookEvent.SESSION_END)


def test_codex_injection_spec_session_start_only() -> None:
    d = descriptor_for(AgentType.CODEX)
    assert d.context_injection is not None
    assert d.context_injection.config_key == "hooks"
    assert d.context_injection.format is ConfigFileFormat.JSON
    assert d.context_injection.events == (HookEvent.SESSION_START,)


def test_every_type_injects_and_its_hook_config_key_is_allowlisted() -> None:
    # The descriptor's injection config_key must resolve in the file allowlist.
    for at in AgentType:
        d = descriptor_for(at)
        assert d.context_injection is not None
        spec = spec_for(at, d.context_injection.config_key)
        assert spec.format is ConfigFileFormat.JSON


def test_native_memory_disable_target_per_type() -> None:
    claude_key, claude_fmt = native_memory_disable_target(AgentType.CLAUDE_CODE)
    assert claude_key == "settings"
    assert claude_fmt is ConfigFileFormat.JSON

    codex_key, codex_fmt = native_memory_disable_target(AgentType.CODEX)
    assert codex_key == "config"
    assert codex_fmt is ConfigFileFormat.TOML


def test_descriptor_has_no_skill_delivery_mode() -> None:
    # Skill delivery collapsed to the single folder model: the master skill
    # folder is symlinked (copy-fallback) into ``<config_dir>/skills``. No
    # delivery-mode discriminator remains on the descriptor.
    from coffer.domain.agent.descriptor import AgentDescriptor

    assert "skill_delivery_mode" not in AgentDescriptor.__dataclass_fields__
