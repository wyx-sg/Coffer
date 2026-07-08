"""The agent capability manifest — one descriptor record per supported agent.

This table is the single source of truth for per-agent behaviour that used to be
scattered across ``switch on AgentType`` sites (``types.py``, ``config_files``,
the MCP services, auto-detect). Adding an agent is adding one
:class:`AgentDescriptor` record; the consumers read the table.

To keep the import graph acyclic, ``types.py`` and ``config_files.py`` define the
low-level primitives (the ``AgentType`` enum, the ``ConfigFileSpec`` dataclass)
and read this table back via a *lazy* import inside their functions — this module
imports them at top level, they import this module only on demand.

Facet fields beyond config-files + MCP (plugins, skills, memory, transcripts)
are added to :class:`AgentDescriptor` by later batches; Batch 1 populates
identity, the config-file allowlist, and MCP injection.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Callable
from dataclasses import dataclass

from coffer.domain.agent.config_files import (
    ConfigFileFormat,
    ConfigFileKind,
    ConfigFileSpec,
)
from coffer.domain.agent.hook_injection import HookEvent, HookInjectionSpec
from coffer.domain.agent.mcp_injection import McpEntryStyle, McpInjectionSpec
from coffer.domain.agent.plugin_capability import (
    PluginCapability,
    PluginModel,
    UninstallStrategy,
)
from coffer.domain.agent.skill_delivery import SkillDeliveryMode
from coffer.domain.agent.types import AgentType


def _home() -> pathlib.Path:
    """Home dir, same source as ``agent.types`` / ``config_files`` so all three
    stay consistent under a test-overridden ``$HOME``."""
    return pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))


@dataclass(frozen=True)
class AgentDescriptor:
    """Everything Coffer needs to know to manage one agent product."""

    type: AgentType
    display_name: str
    #: Standard config directory, relative to ``$HOME`` (e.g. ``.claude``,
    #: ``.codex``). Resolved against the live home at call time.
    config_subpath: str
    #: Builds the curated config-file allowlist, resolved against the agent's
    #: effective config dir.
    config_files: Callable[[pathlib.Path], tuple[ConfigFileSpec, ...]]
    #: How Coffer installs its own ``coffer`` MCP entry (None = MCP not managed).
    mcp: McpInjectionSpec | None = None
    #: How Coffer installs its ``coffer-hook`` lifecycle hooks (None = hooks not
    #: managed). Claude Code installs SessionStart + SessionEnd; Codex installs
    #: SessionStart only (it has no session-end event).
    hooks: HookInjectionSpec | None = None
    #: Allowlist keys of files scanned when listing the agent's *own* MCP
    #: entries (FR-025). Defaults to the MCP injection file when unset.
    mcp_source_keys: tuple[str, ...] = ()
    #: Subpath of the skills-delivery directory under the config dir
    #: (``skills``). Used by the ``FOLDER`` delivery mode.
    skill_subpath: str = "skills"
    #: How Coffer hands a managed skill to this agent. ``FOLDER`` symlinks the
    #: master folder into ``skill_subpath``.
    skill_delivery_mode: SkillDeliveryMode = SkillDeliveryMode.FOLDER
    #: How Coffer manages this agent's plugins (``None`` = no plugin concept).
    plugins: PluginCapability | None = None
    #: Whether this agent is surfaced in discovery — the only UI entry point that
    #: enumerates agents. Both Claude Code and Codex are exposed. The flag gates
    #: discovery/visibility only, never registration — the backend accepts a
    #: direct registration of any manifest type regardless of this flag.
    enabled: bool = True

    def default_config_dir(self) -> pathlib.Path:
        return _home() / self.config_subpath

    def detect_marker(self) -> pathlib.Path:
        # The install root is the config directory for every current agent.
        return self.default_config_dir()

    def default_skill_dir(self) -> pathlib.Path:
        return self.default_config_dir() / self.skill_subpath

    def resolved_mcp_source_keys(self) -> tuple[str, ...]:
        if self.mcp_source_keys:
            return self.mcp_source_keys
        return (self.mcp.config_key,) if self.mcp else ()


# --- config-file allowlist builders (one per agent) ----------------------------


def _claude_code_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    return (
        ConfigFileSpec("settings", "User settings", cfg / "settings.json", ConfigFileFormat.JSON),
        ConfigFileSpec(
            "settings_local",
            "Local settings override",
            cfg / "settings.local.json",
            ConfigFileFormat.JSON,
        ),
        # Claude Code's global state/config file always lives at the home root
        # (``~/.claude.json``), regardless of where the config dir points — it
        # also holds user-scope MCP servers.
        ConfigFileSpec("global", "Global config", _home() / ".claude.json", ConfigFileFormat.JSON),
        ConfigFileSpec(
            "instructions",
            "User instructions (CLAUDE.md)",
            cfg / "CLAUDE.md",
            ConfigFileFormat.MARKDOWN,
        ),
        ConfigFileSpec(
            "subagents",
            "Subagents (agents/)",
            cfg / "agents",
            ConfigFileFormat.MARKDOWN,
            kind=ConfigFileKind.DIRECTORY,
        ),
    )


def _codex_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    return (
        ConfigFileSpec(
            "config", "Config (config.toml)", cfg / "config.toml", ConfigFileFormat.TOML
        ),
        ConfigFileSpec(
            "instructions",
            "Global instructions (AGENTS.md)",
            cfg / "AGENTS.md",
            ConfigFileFormat.MARKDOWN,
        ),
        ConfigFileSpec("hooks", "Hooks (hooks.json)", cfg / "hooks.json", ConfigFileFormat.JSON),
    )


def _opencode_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    # opencode's global config (~/.config/opencode/opencode.json) holds both the
    # `mcp` block (MCP injection) and the `provider` block (provider projection).
    # AGENTS.md is opencode's human-authored instructions file. opencode has no
    # hooks.json (its lifecycle hooks are in-process JS plugins — ADR-040).
    return (
        ConfigFileSpec(
            "opencode", "Config (opencode.json)", cfg / "opencode.json", ConfigFileFormat.JSON
        ),
        ConfigFileSpec(
            "instructions",
            "Global instructions (AGENTS.md)",
            cfg / "AGENTS.md",
            ConfigFileFormat.MARKDOWN,
        ),
    )


def _hermes_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    # Hermes' config.yaml (YAML) holds `mcp_servers`, the `memory` toggles, and
    # the model/provider block. AGENTS.md is its human-authored instructions file.
    return (
        ConfigFileSpec(
            "config", "Config (config.yaml)", cfg / "config.yaml", ConfigFileFormat.YAML
        ),
        ConfigFileSpec(
            "instructions",
            "Global instructions (AGENTS.md)",
            cfg / "AGENTS.md",
            ConfigFileFormat.MARKDOWN,
        ),
    )


def _cursor_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    # Cursor's ~/.cursor/ holds cli-config.json (CLI settings) and, on demand,
    # mcp.json (MCP servers, `mcpServers` map). AGENTS.md is the human-authored
    # instructions file cursor-agent reads.
    return (
        ConfigFileSpec(
            "config", "CLI config (cli-config.json)", cfg / "cli-config.json", ConfigFileFormat.JSON
        ),
        ConfigFileSpec("mcp", "MCP servers (mcp.json)", cfg / "mcp.json", ConfigFileFormat.JSON),
        ConfigFileSpec(
            "instructions",
            "Global instructions (AGENTS.md)",
            cfg / "AGENTS.md",
            ConfigFileFormat.MARKDOWN,
        ),
    )


# --- the manifest --------------------------------------------------------------

AGENT_DESCRIPTORS: dict[AgentType, AgentDescriptor] = {
    AgentType.CLAUDE_CODE: AgentDescriptor(
        type=AgentType.CLAUDE_CODE,
        display_name="Claude Code",
        config_subpath=".claude",
        config_files=_claude_code_files,
        mcp=McpInjectionSpec(
            config_key="global",
            container_key="mcpServers",
            format=ConfigFileFormat.JSON,
            entry_style=McpEntryStyle.COMMAND_MAP,
        ),
        mcp_source_keys=("global", "settings"),
        hooks=HookInjectionSpec(
            config_key="settings",
            format=ConfigFileFormat.JSON,
            events=(HookEvent.SESSION_START, HookEvent.SESSION_END),
        ),
        plugins=PluginCapability(
            model=PluginModel.CLAUDE,
            config_key="settings",
            can_toggle=True,
            # Claude's install inventory is an internal file Coffer never writes,
            # so uninstall is delegated to the `claude plugin uninstall` CLI,
            # which owns that state. Gated at runtime on `claude` being on PATH.
            can_uninstall=True,
            uninstall_strategy=UninstallStrategy.CLI,
        ),
    ),
    AgentType.CODEX: AgentDescriptor(
        type=AgentType.CODEX,
        display_name="OpenAI Codex",
        config_subpath=".codex",
        config_files=_codex_files,
        mcp=McpInjectionSpec(
            config_key="config",
            container_key="mcp_servers",
            format=ConfigFileFormat.TOML,
            entry_style=McpEntryStyle.COMMAND_MAP,
        ),
        mcp_source_keys=("config",),
        hooks=HookInjectionSpec(
            config_key="hooks",
            format=ConfigFileFormat.JSON,
            events=(HookEvent.SESSION_START,),
        ),
        plugins=PluginCapability(
            model=PluginModel.CODEX,
            config_key="config",
            can_toggle=True,
            can_uninstall=True,
        ),
    ),
    AgentType.OPENCODE: AgentDescriptor(
        type=AgentType.OPENCODE,
        display_name="opencode",
        config_subpath=".config/opencode",
        config_files=_opencode_files,
        mcp=McpInjectionSpec(
            config_key="opencode",
            container_key="mcp",
            format=ConfigFileFormat.JSON,
            entry_style=McpEntryStyle.TYPED_LOCAL_OBJECT,
        ),
        # Capability gaps declared as absent facets (surfaces hide the action, they
        # do not fail it) — see the Agent capability matrix in spec 004 / ADR-040:
        #  * hooks=None      — opencode has no shell-command lifecycle hook, only
        #                      in-process JS plugin callbacks; session-context
        #                      injection is a follow-up plugin-drop slice.
        #  * plugins=None    — opencode's plugins are JS modules, a different model
        #                      from Claude/Codex; not managed by Coffer in this slice.
        #  * native memory   — opencode has no cross-session native memory, so it is
        #                      omitted from _NATIVE_MEMORY_DISABLE_TARGET below.
    ),
    AgentType.HERMES: AgentDescriptor(
        type=AgentType.HERMES,
        display_name="Hermes",
        config_subpath=".hermes",
        config_files=_hermes_files,
        mcp=McpInjectionSpec(
            config_key="config",
            container_key="mcp_servers",
            format=ConfigFileFormat.YAML,
            entry_style=McpEntryStyle.COMMAND_MAP,
        ),
        # Native memory IS present (the memory.memory_enabled toggle) — wired in
        # _NATIVE_MEMORY_DISABLE_TARGET below. hooks=None for this slice: hermes'
        # session hooks are a YAML on_session_* / pre_llm_call mechanism distinct
        # from the JSON HookInjectionSpec model (a follow-up slice — ADR-040).
        # plugins=None: hermes plugins are a different model, not managed here.
    ),
    AgentType.CURSOR: AgentDescriptor(
        type=AgentType.CURSOR,
        display_name="Cursor",
        config_subpath=".cursor",
        config_files=_cursor_files,
        mcp=McpInjectionSpec(
            config_key="mcp",
            container_key="mcpServers",
            format=ConfigFileFormat.JSON,
            entry_style=McpEntryStyle.COMMAND_MAP,
        ),
        # Capability gaps (ADR-040 capability matrix) — all absent facets:
        #  * hooks=None            — cursor-agent has a hooks.json, but headless
        #                            firing of SessionStart/End is undocumented
        #                            upstream, so it is deferred (a follow-up slice).
        #  * native memory         — cursor "Memories" is an IDE-only toggle with no
        #                            CLI, so it is omitted from
        #                            _NATIVE_MEMORY_DISABLE_TARGET below.
        #  * provider projection   — cursor is locked to Cursor's own backend with no
        #                            custom LLM base URL, so it is NOT a projection
        #                            target (absent from _AGENT_TARGETS and the
        #                            connection-compatible defaults); cursor-agent
        #                            uses its OWN auth (`cursor-agent login`), which
        #                            Coffer does not inject.
    ),
}


def descriptor_for(agent_type: AgentType) -> AgentDescriptor:
    try:
        return AGENT_DESCRIPTORS[agent_type]
    except KeyError:  # pragma: no cover - every enum value has a record
        raise AssertionError(f"no descriptor for AgentType {agent_type!r}") from None


#: Which allowlisted config file (key + format) holds an agent's native
#: write-side memory toggle (Slice 6). Claude Code → ``settings.json`` (JSON,
#: ``autoMemoryEnabled``); Codex → ``config.toml`` (TOML, ``features.memories``
#: + ``memories.generate_memories``). The transforms live in
#: :mod:`coffer.domain.agent.native_memory_disable`.
_NATIVE_MEMORY_DISABLE_TARGET: dict[AgentType, tuple[str, ConfigFileFormat]] = {
    AgentType.CLAUDE_CODE: ("settings", ConfigFileFormat.JSON),
    AgentType.CODEX: ("config", ConfigFileFormat.TOML),
    # Hermes → config.yaml (YAML) memory.memory_enabled / user_profile_enabled.
    AgentType.HERMES: ("config", ConfigFileFormat.YAML),
}


def native_memory_disable_target(agent_type: AgentType) -> tuple[str, ConfigFileFormat] | None:
    """The ``(config_key, format)`` that holds the native-memory toggle, or ``None``
    for an agent type with no native write-side memory to disable (e.g. opencode —
    see the Agent capability matrix in spec 004 / ADR-040). Callers treat ``None``
    as "this facet is absent" and reject/hide the toggle rather than failing."""
    return _NATIVE_MEMORY_DISABLE_TARGET.get(agent_type)


def is_agent_enabled(agent_type: AgentType) -> bool:
    """Whether this agent is surfaced in discovery/UI. Gates visibility only,
    not registration (see the ``AgentDescriptor.enabled`` field)."""
    return descriptor_for(agent_type).enabled


def visible_agent_types() -> tuple[AgentType, ...]:
    """Agent types currently exposed to users (``enabled=True`` in the manifest)."""
    return tuple(t for t in AgentType if descriptor_for(t).enabled)
