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
import os
import pathlib
import tomllib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import yaml

from coffer.domain.agent.types import AgentType
from coffer.domain.errors import ConfigFileFormatInvalid, ConfigFileNotAllowed


def _home() -> pathlib.Path:
    """Home dir, same source as ``agent.types`` so the two stay consistent."""
    return pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))


class ConfigFileFormat(StrEnum):
    """Format of an allowlisted config file — drives save-time validation."""

    JSON = "json"
    TOML = "toml"
    YAML = "yaml"
    MARKDOWN = "markdown"
    TEXT = "text"


class ConfigFileKind(StrEnum):
    """Whether an allowlist entry is a single file or a directory of files."""

    FILE = "file"
    DIRECTORY = "directory"


@dataclass(frozen=True)
class ConfigFileSpec:
    """One allowlisted config file for an agent type."""

    key: str
    display_name: str
    path: pathlib.Path
    format: ConfigFileFormat
    # For DIRECTORY entries, `format` describes the CHILD files (e.g. the .md
    # subagent definitions), not the directory itself.
    kind: ConfigFileKind = ConfigFileKind.FILE


@dataclass(frozen=True)
class FileStat:
    """Filesystem metadata for an existing file (size in bytes + mtime)."""

    size: int
    modified_at: datetime


@dataclass(frozen=True)
class DirEntryInfo:
    """One child file of a directory-type config entry."""

    relpath: str  # POSIX-style, relative to the directory root
    size: int
    modified_at: datetime


def config_files_for(
    agent_type: AgentType, config_dir: pathlib.Path | None = None
) -> tuple[ConfigFileSpec, ...]:
    """Curated, ordered allowlist of config files for the given agent type.

    Paths resolve against ``config_dir`` (the agent's effective config dir).
    When omitted, the type's standard location is used. Files need not exist —
    `exists` is reported at read/list time by the application layer.
    """
    cfg = config_dir or agent_type.config_dir()
    if agent_type is AgentType.CLAUDE_CODE:
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
            # Claude Code's global state/config file always lives at the home
            # root (``~/.claude.json``), regardless of where the config dir
            # itself points — it also holds user-scope MCP servers. Anchoring
            # it to ``cfg.parent`` was only coincidentally correct for the
            # default ~/.claude and resolved to the wrong file for a custom
            # config_dir, so we anchor it to $HOME directly.
            ConfigFileSpec(
                "global", "Global config", _home() / ".claude.json", ConfigFileFormat.JSON
            ),
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
    if agent_type is AgentType.CODEX:
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
            ConfigFileSpec(
                "hooks", "Hooks (hooks.json)", cfg / "hooks.json", ConfigFileFormat.JSON
            ),
        )
    raise AssertionError(f"unhandled AgentType: {agent_type!r}")  # pragma: no cover


def spec_for(
    agent_type: AgentType, key: str, config_dir: pathlib.Path | None = None
) -> ConfigFileSpec:
    """Return the spec for `key`, or raise `ConfigFileNotAllowed`.

    Callers MUST go through this before any filesystem access so an unknown
    key never touches disk.
    """
    for spec in config_files_for(agent_type, config_dir):
        if spec.key == key:
            return spec
    raise ConfigFileNotAllowed(agent_type.value, key)


def validate_child_relpath(root: pathlib.Path, relpath: str) -> pathlib.Path:
    """Resolve `relpath` under `root` for a directory-type entry.

    Pure path math — no filesystem access (symlink escape is re-checked at
    I/O time by the store). Rejects traversal, absolute paths, backslashes,
    hidden segments, and any extension other than lowercase `.md` (exact:
    `.MD` is rejected so one name can't alias two keys on case-insensitive
    filesystems). Redundant separators (`a//b.md`) normalise away.
    """
    if not root.is_absolute():
        raise ValueError(f"directory-entry root must be absolute, got {root}")
    if not relpath or "\\" in relpath:
        raise ConfigFileNotAllowed("child", relpath or "<empty>")
    p = pathlib.PurePosixPath(relpath)
    if p.is_absolute() or ".." in p.parts or any(part.startswith(".") for part in p.parts):
        raise ConfigFileNotAllowed("child", relpath)
    if p.suffix != ".md":
        raise ConfigFileFormatInvalid("markdown", f"only .md files are allowed, got {relpath!r}")
    return root / pathlib.Path(*p.parts)


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
    elif fmt is ConfigFileFormat.YAML:
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise ConfigFileFormatInvalid("yaml", str(e)) from e
    # markdown / text: nothing to validate.
