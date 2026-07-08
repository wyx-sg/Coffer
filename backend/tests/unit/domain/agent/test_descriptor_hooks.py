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


# --- opencode (ADR-040 re-widen) -----------------------------------------------


def test_opencode_descriptor_identity_and_config_dir() -> None:
    d = descriptor_for(AgentType.OPENCODE)
    assert d.display_name == "opencode"
    assert d.config_subpath == ".config/opencode"
    keys = {s.key for s in d.config_files(d.default_config_dir())}
    assert {"opencode", "instructions"} <= keys


def test_opencode_mcp_spec_is_typed_local_object_in_mcp_container() -> None:
    from coffer.domain.agent.mcp_injection import McpEntryStyle

    d = descriptor_for(AgentType.OPENCODE)
    assert d.mcp is not None
    assert d.mcp.config_key == "opencode"
    assert d.mcp.container_key == "mcp"
    assert d.mcp.format is ConfigFileFormat.JSON
    assert d.mcp.entry_style is McpEntryStyle.TYPED_LOCAL_OBJECT


def test_opencode_has_no_hook_or_native_memory_facet() -> None:
    # Capability gaps are absent facets, not errors (ADR-040): opencode has no
    # shell-command lifecycle hook and no cross-session native memory.
    d = descriptor_for(AgentType.OPENCODE)
    assert d.hooks is None
    assert native_memory_disable_target(AgentType.OPENCODE) is None


# --- hermes (ADR-040 slice 2) --------------------------------------------------


def test_hermes_descriptor_identity_and_mcp() -> None:
    from coffer.domain.agent.mcp_injection import McpEntryStyle

    d = descriptor_for(AgentType.HERMES)
    assert d.display_name == "Hermes"
    assert d.config_subpath == ".hermes"
    keys = {s.key for s in d.config_files(d.default_config_dir())}
    assert {"config", "instructions"} <= keys
    assert d.mcp is not None
    assert d.mcp.config_key == "config"
    assert d.mcp.container_key == "mcp_servers"
    assert d.mcp.format is ConfigFileFormat.YAML
    assert d.mcp.entry_style is McpEntryStyle.COMMAND_MAP


def test_hermes_hooks_deferred_but_native_memory_present() -> None:
    # hooks deferred this slice (YAML on_session_* / pre_llm_call is a new
    # mechanism); native memory IS present (unlike opencode) and wired to YAML.
    d = descriptor_for(AgentType.HERMES)
    assert d.hooks is None
    assert native_memory_disable_target(AgentType.HERMES) == ("config", ConfigFileFormat.YAML)


def test_hermes_config_key_allowlisted_and_yaml() -> None:
    spec = spec_for(AgentType.HERMES, "config")
    assert spec.format is ConfigFileFormat.YAML


# --- cursor (ADR-040 slice 3) --------------------------------------------------


def test_cursor_descriptor_and_mcp() -> None:
    from coffer.domain.agent.mcp_injection import McpEntryStyle

    d = descriptor_for(AgentType.CURSOR)
    assert d.display_name == "Cursor"
    assert d.config_subpath == ".cursor"
    keys = {s.key for s in d.config_files(d.default_config_dir())}
    assert {"config", "mcp", "instructions"} <= keys
    assert d.mcp is not None
    assert d.mcp.config_key == "mcp"
    assert d.mcp.container_key == "mcpServers"
    assert d.mcp.format is ConfigFileFormat.JSON
    assert d.mcp.entry_style is McpEntryStyle.COMMAND_MAP


def test_cursor_facets_all_absent() -> None:
    # cursor is locked to Cursor's backend: hooks deferred, no native memory, and
    # NOT a provider-projection target (ADR-040 capability matrix).
    from coffer.domain.provider.projection import target_for_agent

    d = descriptor_for(AgentType.CURSOR)
    assert d.hooks is None
    assert native_memory_disable_target(AgentType.CURSOR) is None
    assert target_for_agent(AgentType.CURSOR) is None
