"""Config-file allowlist builders — one per agent type (spec agent-registry
"Define a curated config-file allowlist per type").

Split out of ``descriptor.py`` for the file-size limit, exactly as
``plugin_capability.py`` carries its facet's value objects. Each builder returns
the curated :class:`ConfigFileSpec` tuple for one agent, resolved against that
agent's effective config dir; the descriptor table references these by name.
"""

from __future__ import annotations

import os
import pathlib

from coffer.domain.agent.config_files import (
    ConfigFileFormat,
    ConfigFileKind,
    ConfigFileSpec,
)


def _home() -> pathlib.Path:
    """Home dir, same source as ``agent.types`` / ``config_files`` so all three
    stay consistent under a test-overridden ``$HOME``."""
    return pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))


def claude_global_config(cfg: pathlib.Path) -> pathlib.Path:
    """Where Claude Code keeps ``.claude.json`` for the config dir ``cfg``.

    ``$HOME/.claude.json`` for the default ``~/.claude`` (``CLAUDE_CONFIG_DIR``
    unset); ``<cfg>/.claude.json`` for any other dir, because the only way
    Claude Code reads a non-default config dir is ``CLAUDE_CONFIG_DIR``, and
    then it keeps the file inside that dir and never reads the home one.
    Probed on Claude Code 2.1.281 with a throwaway ``HOME``: ``claude mcp add
    -s user`` under ``CLAUDE_CONFIG_DIR=$T/cfg`` wrote ``$T/cfg/.claude.json``,
    and ``claude mcp get`` did not see a server kept in ``$HOME/.claude.json``.
    One answer for every reader — the ``global`` allowlist key (MCP install
    target, MCP-entry source, config-file editor) and model discovery — per
    spec agent-registry/claude-code "Allowlist exactly the files Claude Code
    reads".
    """
    default = _home() / ".claude"
    if cfg.expanduser().resolve() == default.resolve():
        return _home() / ".claude.json"
    return cfg / ".claude.json"


def _claude_code_files(cfg: pathlib.Path) -> tuple[ConfigFileSpec, ...]:
    return (
        ConfigFileSpec("settings", "User settings", cfg / "settings.json", ConfigFileFormat.JSON),
        ConfigFileSpec(
            "settings_local",
            "Local settings override",
            cfg / "settings.local.json",
            ConfigFileFormat.JSON,
        ),
        # Claude Code's global state/config file — it also holds user-scope MCP
        # servers. Beside the default dir, inside a custom one.
        ConfigFileSpec("global", "Global config", claude_global_config(cfg), ConfigFileFormat.JSON),
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
