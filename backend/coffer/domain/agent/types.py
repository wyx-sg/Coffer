"""Supported agent types + their default install/skill directories.

Pure domain code — no I/O, no platform calls at module top level. Defaults
are computed on demand (`default_skill_dir()` / `detect_marker()` /
`config_dir()`).

v1 supports exactly two products. Each value covers both the CLI and the
app/IDE form of that product, which share one config directory.
"""

from __future__ import annotations

import os
import pathlib
from enum import StrEnum


class AgentType(StrEnum):
    """v1 supported agent products."""

    CLAUDE_CODE = "claude_code"
    CODEX = "codex"

    @property
    def display_name(self) -> str:
        return _DISPLAY[self]

    def default_name(self) -> str:
        """Stable default resource name when the user does not supply one.

        Mirrors auto-detect naming so a manually-added agent with a blank
        name lands on the same identifier auto-detection would have used:
        underscores become hyphens (e.g. ``claude_code`` -> ``claude-code``).
        """
        return self.value.replace("_", "-")

    def default_skill_dir(self) -> pathlib.Path:
        """Path agents read skills from. Computed per host platform.

        Used when the user does not override `skill_dir` at registration.
        The path is **not** required to exist — registration validates
        writability separately.
        """
        return _default_skill_dir(self)

    def detect_marker(self) -> pathlib.Path:
        """Path checked during auto-detection; usually the parent of the
        default skill directory."""
        return _detect_marker(self)

    def config_dir(self) -> pathlib.Path:
        """Root the config-file allowlist resolves against (`~/.claude`,
        `~/.codex`). Distinct from `default_skill_dir()` (a subdir)."""
        return _config_dir(self)


_DISPLAY: dict[AgentType, str] = {
    AgentType.CLAUDE_CODE: "Claude Code",
    AgentType.CODEX: "OpenAI Codex",
}


def _home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))


def _config_dir(t: AgentType) -> pathlib.Path:
    if t is AgentType.CLAUDE_CODE:
        return _home() / ".claude"
    if t is AgentType.CODEX:
        return _home() / ".codex"
    raise AssertionError(f"unhandled AgentType: {t!r}")  # pragma: no cover


def _default_skill_dir(t: AgentType) -> pathlib.Path:
    return _config_dir(t) / "skills"


def _detect_marker(t: AgentType) -> pathlib.Path:
    # For all v1 types the install root is the config directory (the parent
    # of the default skill dir).
    return _config_dir(t)
