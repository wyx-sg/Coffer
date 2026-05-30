"""Curated config-file allowlist per agent type + format validation.

Pure domain code. Path construction reads `os.environ['HOME']` (same pattern
as `types.py`) but performs no other I/O — existence checks, reads, and writes
happen in the application/infrastructure layers.

The allowlist is the security boundary: surfaces address config files by a
stable `key`, never by a caller-supplied path, so path traversal is impossible
by construction. An unknown key raises `ConfigFileNotAllowed` (→ 404) before
any filesystem access.
"""

from __future__ import annotations

import json
import pathlib
import tomllib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from coffer.domain.agent.types import AgentType
from coffer.domain.errors import ConfigFileFormatInvalid, ConfigFileNotAllowed


class ConfigFileFormat(StrEnum):
    """Format of an allowlisted config file — drives save-time validation."""

    JSON = "json"
    TOML = "toml"
    MARKDOWN = "markdown"
    TEXT = "text"


@dataclass(frozen=True)
class ConfigFileSpec:
    """One allowlisted config file for an agent type."""

    key: str
    display_name: str
    path: pathlib.Path
    format: ConfigFileFormat


@dataclass(frozen=True)
class FileStat:
    """Filesystem metadata for an existing file (size in bytes + mtime)."""

    size: int
    modified_at: datetime


def _home() -> pathlib.Path:
    import os

    return pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))


def config_files_for(agent_type: AgentType) -> tuple[ConfigFileSpec, ...]:
    """Curated, ordered allowlist of config files for the given agent type.

    Paths are resolved per host. Files need not exist — `exists` is reported
    at read/list time by the application layer.
    """
    if agent_type is AgentType.CLAUDE_CODE:
        cfg = agent_type.config_dir()  # ~/.claude
        return (
            ConfigFileSpec(
                "settings", "User settings", cfg / "settings.json", ConfigFileFormat.JSON
            ),
            ConfigFileSpec(
                "settings_local",
                "Local settings override",
                cfg / "settings.local.json",
                ConfigFileFormat.JSON,
            ),
            # The global state/config file lives at the home root, not under
            # ~/.claude. It also holds the user-scope MCP servers.
            ConfigFileSpec(
                "global", "Global config", _home() / ".claude.json", ConfigFileFormat.JSON
            ),
            ConfigFileSpec(
                "memory", "User memory (CLAUDE.md)", cfg / "CLAUDE.md", ConfigFileFormat.MARKDOWN
            ),
        )
    if agent_type is AgentType.CODEX:
        cfg = agent_type.config_dir()  # ~/.codex
        return (
            ConfigFileSpec(
                "config", "Config (config.toml)", cfg / "config.toml", ConfigFileFormat.TOML
            ),
            ConfigFileSpec(
                "memory",
                "Global instructions (AGENTS.md)",
                cfg / "AGENTS.md",
                ConfigFileFormat.MARKDOWN,
            ),
        )
    raise AssertionError(f"unhandled AgentType: {agent_type!r}")  # pragma: no cover


def spec_for(agent_type: AgentType, key: str) -> ConfigFileSpec:
    """Return the spec for `key`, or raise `ConfigFileNotAllowed`.

    Callers MUST go through this before any filesystem access so an unknown
    key never touches disk.
    """
    for spec in config_files_for(agent_type):
        if spec.key == key:
            return spec
    raise ConfigFileNotAllowed(agent_type.value, key)


def validate_content(fmt: ConfigFileFormat, text: str) -> None:
    """Raise `ConfigFileFormatInvalid` if `text` is malformed for `fmt`.

    `markdown` and `text` are always accepted. `json`/`toml` must parse.
    """
    if fmt is ConfigFileFormat.JSON:
        try:
            json.loads(text)
        except ValueError as e:
            raise ConfigFileFormatInvalid("json", str(e)) from e
    elif fmt is ConfigFileFormat.TOML:
        try:
            tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            raise ConfigFileFormatInvalid("toml", str(e)) from e
    # markdown / text: nothing to validate.
