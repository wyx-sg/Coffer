"""The agent capability manifest — one descriptor record per supported agent.

This table is the single source of truth for per-agent behaviour that used to be
scattered across ``switch on AgentType`` sites (``types.py``, ``config_files``,
the MCP services, auto-detect). Adding an agent is adding one
:class:`AgentDescriptor` record; the consumers read the table.

To keep the import graph acyclic, ``types.py`` and ``config_files.py`` define the
low-level primitives (the ``AgentType`` enum, the ``ConfigFileSpec`` dataclass)
and read this table back via a *lazy* import inside their functions — this module
imports them at top level, they import this module only on demand.

:class:`AgentDescriptor` carries every per-type answer Coffer needs: identity,
the config-file allowlist, MCP injection, the skill directory, and the plugin
capability.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable
from dataclasses import dataclass

from coffer.domain.agent.allowlists import _claude_code_files, _codex_files, _home
from coffer.domain.agent.config_files import ConfigFileFormat, ConfigFileSpec
from coffer.domain.agent.mcp_injection import McpEntryStyle, McpInjectionSpec
from coffer.domain.agent.plugin_capability import (
    PluginCapability,
    PluginModel,
    UninstallStrategy,
)
from coffer.domain.agent.types import AgentType


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
    #: Allowlist keys of files scanned when listing the agent's *own* MCP
    #: entries (spec agent-registry "List the MCP entries in the agent's own
    #: config files"). Defaults to the MCP injection file when unset.
    mcp_source_keys: tuple[str, ...] = ()
    #: Subpath of the skills-delivery directory under the config dir
    #: (``skills``). Coffer delivers a managed skill by symlinking (copy
    #: fallback) the master folder into it.
    skill_subpath: str = "skills"
    #: The environment variable the agent's own runtime reads a non-default
    #: config directory from (``CLAUDE_CONFIG_DIR``, ``CODEX_HOME``). Every
    #: process Coffer spawns to run the agent carries it for a custom
    #: ``config_dir`` — see :func:`coffer.domain.agent.home_env.home_env`.
    home_env_var: str = ""
    #: How Coffer manages this agent's plugins (``None`` = no plugin concept).
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


# --- the manifest --------------------------------------------------------------

AGENT_DESCRIPTORS: dict[AgentType, AgentDescriptor] = {
    AgentType.CLAUDE_CODE: AgentDescriptor(
        type=AgentType.CLAUDE_CODE,
        display_name="Claude Code",
        config_subpath=".claude",
        config_files=_claude_code_files,
        home_env_var="CLAUDE_CONFIG_DIR",
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
        home_env_var="CODEX_HOME",
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
}


def descriptor_for(agent_type: AgentType) -> AgentDescriptor:
    try:
        return AGENT_DESCRIPTORS[agent_type]
    except KeyError:  # pragma: no cover - every enum value has a record
        raise AssertionError(f"no descriptor for AgentType {agent_type!r}") from None


# An ``enabled`` flag used to sit on the descriptor, gating whether a type was
# offered by auto-detect. It was True for every record it ever held, and it
# gated discovery only while registration accepted any manifest type anyway —
# so its only reachable effect would have been hiding an agent from the one
# screen that helps a user add it. Withdrawing an agent means removing it from
# ``AgentType`` and this manifest, which stops registration too; 0031 and 0048
# are how that was actually done.
