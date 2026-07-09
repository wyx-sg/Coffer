"""Config-file allowlist builders — one per agent type (spec 004 FR-013).

Split out of ``descriptor.py`` for the file-size limit, exactly as
``skill_delivery.py`` and ``plugin_capability.py`` carry their facets' value
objects. Each builder returns the curated :class:`ConfigFileSpec` tuple for one
agent, resolved against that agent's effective config dir; the descriptor table
references these by name.
"""

from __future__ import annotations

import os
import pathlib

from coffer.domain.agent.config_files import (
    ConfigFileFormat,
    ConfigFileKind,
    ConfigFileSpec,
)
from coffer.domain.agent.plugin_drop import PLUGIN_SUBDIR


def _home() -> pathlib.Path:
    """Home dir, same source as ``agent.types`` / ``config_files`` so all three
    stay consistent under a test-overridden ``$HOME``."""
    return pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))


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
    # `mcp` block (MCP injection) and the `provider` block (provider projection);
    # opencode loads and MERGES config.json / opencode.json / opencode.jsonc, so
    # Coffer's writes to opencode.json coexist with a user-authored .jsonc
    # (probe-verified, 1.14.48). AGENTS.md is opencode's human-authored
    # instructions file. opencode has no hooks.json — its lifecycle hooks are
    # in-process JS plugins auto-loaded from `plugin/`, which is where Coffer
    # drops its session-context plugin (PLUGIN_DROP, ADR-042).
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
        ConfigFileSpec(
            "plugin",
            "Plugins (plugin/)",
            cfg / PLUGIN_SUBDIR,
            ConfigFileFormat.TEXT,
            kind=ConfigFileKind.DIRECTORY,
        ),
    )


def _hermes_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    # Hermes' config.yaml (YAML) holds `mcp_servers`, the `memory` toggles, and
    # the model/provider block. SOUL.md is the ONLY instruction file hermes
    # reads from its home dir (`prompt_builder.load_soul_md`, identity slot #1,
    # every platform incl. ACP) — AGENTS.md is resolved against the session
    # *cwd* only (`build_context_files_prompt`: "AGENTS.md (cwd only)"), so a
    # `~/.hermes/AGENTS.md` is dead weight and is not allowlisted. Both facts
    # probe-verified against hermes v0.18.0 (marker in SOUL.md reaches the
    # system prompt; marker in ~/.hermes/AGENTS.md does not).
    return (
        ConfigFileSpec(
            "config", "Config (config.yaml)", cfg / "config.yaml", ConfigFileFormat.YAML
        ),
        ConfigFileSpec(
            "soul",
            "Persona & global instructions (SOUL.md)",
            cfg / "SOUL.md",
            ConfigFileFormat.MARKDOWN,
        ),
    )


def _openclaw_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    # openclaw's ~/.openclaw/openclaw.json (plain JSON) holds the `mcp.servers`
    # block (MCP injection), the `models.providers` block (provider projection),
    # and the `plugins.entries` / `plugins.slots` blocks (Coffer's dropped
    # extension enable flag + native-memory disable). Its human-facing
    # instruction files live in the agent WORKSPACE — `agents.defaults.workspace`,
    # default `<cfg>/workspace` (live-verified on openclaw 2026.6.11); the paths
    # below assume that default (a relocated workspace simply lists as absent).
    # `extensions/` is where openclaw discovers local plugin PACKAGE DIRS —
    # Coffer's session-context extension is dropped there (PLUGIN_DROP, FR-048);
    # the directory viewer lists `.md` children only, so the package's JS/JSON
    # files are managed exclusively through the install/uninstall operations.
    ws = cfg / "workspace"
    return (
        ConfigFileSpec(
            "config", "Config (openclaw.json)", cfg / "openclaw.json", ConfigFileFormat.JSON
        ),
        ConfigFileSpec(
            "instructions",
            "Workspace instructions (AGENTS.md)",
            ws / "AGENTS.md",
            ConfigFileFormat.MARKDOWN,
        ),
        ConfigFileSpec("soul", "Persona (SOUL.md)", ws / "SOUL.md", ConfigFileFormat.MARKDOWN),
        ConfigFileSpec(
            "identity", "Identity (IDENTITY.md)", ws / "IDENTITY.md", ConfigFileFormat.MARKDOWN
        ),
        ConfigFileSpec("user", "User profile (USER.md)", ws / "USER.md", ConfigFileFormat.MARKDOWN),
        ConfigFileSpec(
            "tools", "Tool notes (TOOLS.md)", ws / "TOOLS.md", ConfigFileFormat.MARKDOWN
        ),
        ConfigFileSpec(
            "memory",
            "Curated memory (MEMORY.md)",
            ws / "MEMORY.md",
            ConfigFileFormat.MARKDOWN,
        ),
        ConfigFileSpec(
            "extensions",
            "Extensions (extensions/)",
            cfg / "extensions",
            ConfigFileFormat.TEXT,
            kind=ConfigFileKind.DIRECTORY,
        ),
    )


def _cursor_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    # Cursor's ~/.cursor/ holds cli-config.json (CLI settings) and, on demand,
    # mcp.json (MCP servers, `mcpServers` map) and hooks.json (lifecycle hooks,
    # its own flat-entry shape). AGENTS.md is the human-authored instructions
    # file cursor-agent reads.
    return (
        ConfigFileSpec(
            "config", "CLI config (cli-config.json)", cfg / "cli-config.json", ConfigFileFormat.JSON
        ),
        ConfigFileSpec("mcp", "MCP servers (mcp.json)", cfg / "mcp.json", ConfigFileFormat.JSON),
        ConfigFileSpec("hooks", "Hooks (hooks.json)", cfg / "hooks.json", ConfigFileFormat.JSON),
        ConfigFileSpec(
            "instructions",
            "Global instructions (AGENTS.md)",
            cfg / "AGENTS.md",
            ConfigFileFormat.MARKDOWN,
        ),
    )
