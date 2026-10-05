"""Curated config-file allowlist per agent type.

Pure domain code. Path construction reads `os.environ['HOME']` (same pattern
as `types.py`) but performs no other I/O — existence checks, reads, and writes
happen in the application/infrastructure layers.

The allowlist is the security boundary: surfaces address config files by a
stable `key`, never by a caller-supplied path, so path traversal is impossible
by construction. An unknown key raises `ConfigFileNotAllowed` (→ 404) before
any filesystem access.
"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from coffer.domain.agent.types import AgentType
from coffer.domain.errors import ConfigFileNotAllowed


def _home() -> pathlib.Path:
    """Home dir, same source as ``agent.types`` so the two stay consistent."""
    return pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))


class ConfigFileFormat(StrEnum):
    """Format of an allowlisted config file."""

    JSON = "json"
    TOML = "toml"
    MARKDOWN = "markdown"


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
    path: str  # absolute path, for the open / reveal affordances
    size: int
    modified_at: datetime


@dataclass(frozen=True)
class FileText:
    """A config file's text as read for a preview: capped, never guessed at.

    ``content`` is empty when ``binary``; ``size`` is the file's true length
    even when ``truncated``.
    """

    content: str
    size: int
    truncated: bool
    binary: bool


def config_files_for(
    agent_type: AgentType, config_dir: pathlib.Path | None = None
) -> tuple[ConfigFileSpec, ...]:
    """Curated, ordered allowlist of config files for the given agent type.

    Paths resolve against ``config_dir`` (the agent's effective config dir).
    When omitted, the type's standard location is used. Files need not exist —
    `exists` is reported at read/list time by the application layer.
    """
    # Lazy import keeps the manifest's import of this module (for ConfigFileSpec)
    # acyclic — the manifest owns the per-agent allowlist data.
    from coffer.domain.agent.descriptor import descriptor_for

    cfg = config_dir or agent_type.config_dir()
    return descriptor_for(agent_type).config_files(cfg)


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
