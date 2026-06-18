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
    #: ``.config/opencode``). Resolved against the live home at call time.
    config_subpath: str
    #: Builds the curated config-file allowlist, resolved against the agent's
    #: effective config dir.
    config_files: Callable[[pathlib.Path], tuple[ConfigFileSpec, ...]]
    #: How Coffer installs its own ``coffer`` MCP entry (None = MCP not managed).
    mcp: McpInjectionSpec | None = None
    #: Allowlist keys of files scanned when listing the agent's *own* MCP
    #: entries (FR-025). Defaults to the MCP injection file when unset.
    mcp_source_keys: tuple[str, ...] = ()
    #: Subpath of the skills-delivery directory under the config dir
    #: (``skills`` for most; OpenClaw nests under ``workspace``). Used by the
    #: ``FOLDER`` delivery mode.
    skill_subpath: str = "skills"
    #: How Coffer hands a managed skill to this agent. ``FOLDER`` symlinks the
    #: master folder into ``skill_subpath``; the others (Cursor ``RULES_MDC``,
    #: Hermes ``EXTERNAL_DIR``) are recognized extension points not yet
    #: delivered — skill-enable for them fails cleanly rather than mis-delivers.
    skill_delivery_mode: SkillDeliveryMode = SkillDeliveryMode.FOLDER
    #: How Coffer manages this agent's plugins (``None`` = no plugin concept,
    #: e.g. Hermes where MCP *is* the plugin mechanism — empty listing, toggle
    #: and uninstall unsupported).
    plugins: PluginCapability | None = None
    #: Whether this agent is surfaced in the UI. Only Claude Code and Codex are
    #: fully tested today; the rest are wired in the manifest (so the retained
    #: distill/projection/skill-delivery code can still reference them) but
    #: hidden from discovery — the only UI entry point that enumerates agents —
    #: until they are validated. The backend still accepts a direct registration
    #: of any manifest type (the retained multi-agent features depend on it);
    #: this flag gates discovery/visibility, not registration. Flipping it back
    #: to ``True`` re-exposes the agent.
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


def _cursor_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    return (
        ConfigFileSpec("mcp", "MCP servers (mcp.json)", cfg / "mcp.json", ConfigFileFormat.JSON),
        # Global ~/.cursor/.cursorrules — the per-project .cursor/rules/*.mdc are
        # project-scoped, not config-dir files, so they stay out of the allowlist.
        ConfigFileSpec(
            "rules", "Rules (.cursorrules)", cfg / ".cursorrules", ConfigFileFormat.MARKDOWN
        ),
        ConfigFileSpec(
            "instructions", "Instructions (AGENTS.md)", cfg / "AGENTS.md", ConfigFileFormat.MARKDOWN
        ),
    )


def _opencode_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    return (
        ConfigFileSpec(
            "config", "Config (opencode.json)", cfg / "opencode.json", ConfigFileFormat.JSON
        ),
        ConfigFileSpec(
            "instructions", "Instructions (AGENTS.md)", cfg / "AGENTS.md", ConfigFileFormat.MARKDOWN
        ),
        ConfigFileSpec(
            "subagents",
            "Subagents (agents/)",
            cfg / "agents",
            ConfigFileFormat.MARKDOWN,
            kind=ConfigFileKind.DIRECTORY,
        ),
        ConfigFileSpec(
            "commands",
            "Commands (commands/)",
            cfg / "commands",
            ConfigFileFormat.MARKDOWN,
            kind=ConfigFileKind.DIRECTORY,
        ),
    )


def _openclaw_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    # openclaw.json is JSON5; in practice comment-free configs parse as JSON.
    # JSON5-specific syntax support is a follow-up if real configs need it.
    # OpenClaw's instructions/identity surface is not reliably documented, so no
    # instructions entry is added until the file is confirmed.
    return (
        ConfigFileSpec(
            "config", "Config (openclaw.json)", cfg / "openclaw.json", ConfigFileFormat.JSON
        ),
    )


def _hermes_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    return (
        ConfigFileSpec(
            "config", "Config (config.yaml)", cfg / "config.yaml", ConfigFileFormat.YAML
        ),
        ConfigFileSpec(
            "instructions", "Identity (SOUL.md)", cfg / "SOUL.md", ConfigFileFormat.MARKDOWN
        ),
        ConfigFileSpec(
            "identity_user", "Identity (USER.md)", cfg / "USER.md", ConfigFileFormat.MARKDOWN
        ),
        ConfigFileSpec(
            "cron",
            "Cron jobs (cron/)",
            cfg / "cron",
            ConfigFileFormat.MARKDOWN,
            kind=ConfigFileKind.DIRECTORY,
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
        plugins=PluginCapability(
            model=PluginModel.CODEX,
            config_key="config",
            can_toggle=True,
            can_uninstall=True,
        ),
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
        # Cursor consumes skills as .mdc rule files, not symlinked folders —
        # a recognized extension point that a follow-up wires end-to-end.
        skill_delivery_mode=SkillDeliveryMode.RULES_MDC,
        # Read-only VSIX list; enable/disable lives in Cursor's SQLite (internal
        # state), so there is no write surface (config_key=None) and neither
        # toggle nor uninstall is supported.
        plugins=PluginCapability(
            model=PluginModel.CURSOR_RO,
            config_key=None,
            can_toggle=False,
            can_uninstall=False,
        ),
        enabled=False,
    ),
    AgentType.OPENCODE: AgentDescriptor(
        type=AgentType.OPENCODE,
        display_name="OpenCode",
        config_subpath=".config/opencode",
        config_files=_opencode_files,
        mcp=McpInjectionSpec(
            config_key="config",
            container_key="mcp",
            format=ConfigFileFormat.JSON,
            entry_style=McpEntryStyle.TYPED_COMMAND_ARRAY,
        ),
        plugins=PluginCapability(
            model=PluginModel.OPENCODE,
            config_key="config",
            can_toggle=True,
            can_uninstall=True,
        ),
        enabled=False,
    ),
    AgentType.OPENCLAW: AgentDescriptor(
        type=AgentType.OPENCLAW,
        display_name="OpenClaw",
        config_subpath=".openclaw",
        config_files=_openclaw_files,
        mcp=McpInjectionSpec(
            config_key="config",
            container_key="mcp",
            format=ConfigFileFormat.JSON,
            entry_style=McpEntryStyle.COMMAND_MAP,
        ),
        # OpenClaw reads skills from workspace/skills, so a delivered skill
        # lands at workspace/skills/<name>/SKILL.md (FOLDER mode).
        skill_subpath="workspace/skills",
        # OpenClaw's plugins{} schema is only partly documented; the transforms
        # are tolerant (see plugin_state_extra.py).
        plugins=PluginCapability(
            model=PluginModel.OPENCLAW,
            config_key="config",
            can_toggle=True,
            can_uninstall=True,
        ),
        enabled=False,
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
        # Hermes registers skills as external directories, not symlinked
        # folders — a recognized extension point not yet delivered.
        skill_delivery_mode=SkillDeliveryMode.EXTERNAL_DIR,
        enabled=False,
    ),
}


def descriptor_for(agent_type: AgentType) -> AgentDescriptor:
    try:
        return AGENT_DESCRIPTORS[agent_type]
    except KeyError:  # pragma: no cover - every enum value has a record
        raise AssertionError(f"no descriptor for AgentType {agent_type!r}") from None


def is_agent_enabled(agent_type: AgentType) -> bool:
    """Whether this agent is surfaced in the UI and accepted for registration."""
    return descriptor_for(agent_type).enabled


def visible_agent_types() -> tuple[AgentType, ...]:
    """Agent types currently exposed to users (``enabled=True`` in the manifest)."""
    return tuple(t for t in AgentType if descriptor_for(t).enabled)
