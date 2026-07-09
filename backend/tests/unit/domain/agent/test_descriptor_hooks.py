"""Descriptor context-injection + native-memory facets (ADR-042).

Claude Code installs SessionStart + SessionEnd into ``settings`` (JSON); Codex
and Cursor install SessionStart only — neither has a usable session-end event.
Cursor's hooks file uses its own flavor (flat entries, camelCase event keys).
The native-memory-disable facet records which file+format holds the toggle.
"""

from __future__ import annotations

from coffer.domain.agent.config_files import ConfigFileFormat, spec_for
from coffer.domain.agent.context_injection import HookEvent, HookFlavor, InjectionMode
from coffer.domain.agent.descriptor import descriptor_for, native_memory_disable_target
from coffer.domain.agent.types import AgentType


def test_claude_code_injection_spec() -> None:
    d = descriptor_for(AgentType.CLAUDE_CODE)
    assert d.context_injection is not None
    assert d.context_injection.mode is InjectionMode.SHELL_COMMAND
    assert d.context_injection.flavor is HookFlavor.CLAUDE
    assert d.context_injection.config_key == "settings"
    assert d.context_injection.format is ConfigFileFormat.JSON
    assert d.context_injection.events == (HookEvent.SESSION_START, HookEvent.SESSION_END)
    assert d.context_injection.container_key == "hooks"


def test_codex_injection_spec_session_start_only() -> None:
    d = descriptor_for(AgentType.CODEX)
    assert d.context_injection is not None
    assert d.context_injection.mode is InjectionMode.SHELL_COMMAND
    assert d.context_injection.flavor is HookFlavor.CLAUDE
    assert d.context_injection.config_key == "hooks"
    assert d.context_injection.format is ConfigFileFormat.JSON
    assert d.context_injection.events == (HookEvent.SESSION_START,)


def test_hook_config_keys_are_allowlisted() -> None:
    # The descriptor's injection config_key must resolve in the file allowlist.
    for at in (AgentType.CLAUDE_CODE, AgentType.CODEX, AgentType.CURSOR):
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


def test_opencode_has_no_shell_hook_or_native_memory_facet() -> None:
    # Absent facets, not errors (ADR-042): opencode has no shell-command hook (its
    # JS plugin API is a PLUGIN_DROP slice) and no cross-session native memory.
    d = descriptor_for(AgentType.OPENCODE)
    assert d.context_injection is None
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


def test_hermes_hooks_absent_but_native_memory_present() -> None:
    # hermes' session hooks are documented but never invoked upstream
    # (hermes-agent#2817, won't fix) — INSTRUCTIONS_BLOCK is the fallback slice.
    # Native memory IS present (unlike opencode) and wired to YAML.
    d = descriptor_for(AgentType.HERMES)
    assert d.context_injection is None
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
    assert {"config", "mcp", "hooks", "instructions"} <= keys
    assert d.mcp is not None
    assert d.mcp.config_key == "mcp"
    assert d.mcp.container_key == "mcpServers"
    assert d.mcp.format is ConfigFileFormat.JSON
    assert d.mcp.entry_style is McpEntryStyle.COMMAND_MAP


def test_cursor_injection_spec_uses_cursor_flavor() -> None:
    # cursor's hooks.json documents `sessionStart` with an `additional_context`
    # output — a real injection point, in its own flavor (ADR-042).
    d = descriptor_for(AgentType.CURSOR)
    assert d.context_injection is not None
    assert d.context_injection.mode is InjectionMode.SHELL_COMMAND
    assert d.context_injection.flavor is HookFlavor.CURSOR
    assert d.context_injection.config_key == "hooks"
    assert d.context_injection.events == (HookEvent.SESSION_START,)


def test_cursor_provider_and_native_memory_facets_absent() -> None:
    # cursor-agent is locked to Cursor's own backend (no custom base URL) and its
    # Memories toggle is IDE-only — both remain absent facets (ADR-042 matrix).
    from coffer.domain.provider.projection import target_for_agent

    assert native_memory_disable_target(AgentType.CURSOR) is None
    assert target_for_agent(AgentType.CURSOR) is None
