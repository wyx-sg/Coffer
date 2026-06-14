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
from enum import StrEnum

from coffer.domain.agent.config_files import (
    ConfigFileFormat,
    ConfigFileKind,
    ConfigFileSpec,
)
from coffer.domain.agent.mcp_injection import McpEntryStyle, McpInjectionSpec
from coffer.domain.agent.types import AgentType


class PluginModel(StrEnum):
    """Which plugin parse/toggle/uninstall strategy an agent uses.

    The :class:`AgentPluginService` dispatches on this discriminator instead of
    switching on :class:`AgentType`, so adding an agent's plugin support is data
    (a :class:`PluginCapability` record), not a new ``if`` branch.
    """

    #: Claude Code — 3 internal/settings files; toggle writes settings only.
    CLAUDE = "claude"
    #: Codex — ``[plugins."<id>"]`` tables in config.toml + a cache dir.
    CODEX = "codex"
    #: Cursor — read-only VSIX list from ``extensions.json`` (array).
    CURSOR_RO = "cursor_ro"
    #: OpenCode — the ``plugin`` array in opencode.json.
    OPENCODE = "opencode"
    #: OpenClaw — the ``plugins`` block in openclaw.json.
    OPENCLAW = "openclaw"


@dataclass(frozen=True)
class PluginCapability:
    """How Coffer manages one agent's plugins (the plugin facet of the manifest).

    Carries enough for the service to dispatch without a type switch: the
    ``model`` strategy discriminator, the allowlist ``config_key`` of the write
    surface (``None`` for list-only agents), and capability flags.
    """

    model: PluginModel
    #: Allowlist key of the file the toggle/uninstall transforms write
    #: (``"settings"`` for Claude, ``"config"`` for the rest; ``None`` =
    #: list-only, no write surface).
    config_key: str | None
    can_toggle: bool = True
    can_uninstall: bool = False


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
    #: (``skills`` for most; OpenClaw nests under ``workspace``). Refined by the
    #: skill-delivery batch.
    skill_subpath: str = "skills"
    #: How Coffer manages this agent's plugins (``None`` = no plugin concept,
    #: e.g. Hermes where MCP *is* the plugin mechanism — empty listing, toggle
    #: and uninstall unsupported).
    plugins: PluginCapability | None = None

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
    )


def _opencode_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    return (
        ConfigFileSpec(
            "config", "Config (opencode.json)", cfg / "opencode.json", ConfigFileFormat.JSON
        ),
        ConfigFileSpec(
            "instructions", "Instructions (AGENTS.md)", cfg / "AGENTS.md", ConfigFileFormat.MARKDOWN
        ),
    )


def _openclaw_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    # openclaw.json is JSON5; in practice comment-free configs parse as JSON.
    # JSON5-specific syntax support is a follow-up if real configs need it.
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
            can_uninstall=False,
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
        # Read-only VSIX list; enable/disable lives in Cursor's SQLite (internal
        # state), so there is no write surface (config_key=None) and neither
        # toggle nor uninstall is supported.
        plugins=PluginCapability(
            model=PluginModel.CURSOR_RO,
            config_key=None,
            can_toggle=False,
            can_uninstall=False,
        ),
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
        # NOTE: OpenClaw's real skills dir is workspace/skills; kept flat here
        # until the skill-delivery batch wires per-agent skill targets.
        # OpenClaw's plugins{} schema is only partly documented; the transforms
        # are tolerant (see plugin_state_extra.py).
        plugins=PluginCapability(
            model=PluginModel.OPENCLAW,
            config_key="config",
            can_toggle=True,
            can_uninstall=True,
        ),
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
    ),
}


def descriptor_for(agent_type: AgentType) -> AgentDescriptor:
    try:
        return AGENT_DESCRIPTORS[agent_type]
    except KeyError:  # pragma: no cover - every enum value has a record
        raise AssertionError(f"no descriptor for AgentType {agent_type!r}") from None
