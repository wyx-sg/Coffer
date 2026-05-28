"""Supported agent types + their default install/skill directories.

Pure domain code — no I/O, no platform calls at module top level. Defaults
are computed on demand (`default_skill_dir()` / `detect_marker()`).
"""

from __future__ import annotations

import os
import pathlib
import sys
from enum import StrEnum


class AgentType(StrEnum):
    """v1 supported agent products."""

    CLAUDE_CODE = "claude_code"
    CLAUDE_DESKTOP = "claude_desktop"
    CURSOR = "cursor"
    CODEX_CLI = "codex_cli"

    @property
    def display_name(self) -> str:
        return _DISPLAY[self]

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


_DISPLAY: dict[AgentType, str] = {
    AgentType.CLAUDE_CODE: "Claude Code",
    AgentType.CLAUDE_DESKTOP: "Claude Desktop",
    AgentType.CURSOR: "Cursor",
    AgentType.CODEX_CLI: "OpenAI Codex CLI",
}


def _home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))


def _appdata() -> pathlib.Path:
    """Windows %APPDATA% fallback for non-Windows runs (used in tests)."""
    raw = os.environ.get("APPDATA")
    if raw:
        return pathlib.Path(raw)
    return _home() / "AppData" / "Roaming"


def _default_skill_dir(t: AgentType) -> pathlib.Path:
    if t is AgentType.CLAUDE_CODE:
        return _home() / ".claude" / "skills"
    if t is AgentType.CLAUDE_DESKTOP:
        if sys.platform == "darwin":
            return _home() / "Library" / "Application Support" / "Claude" / "skills"
        if sys.platform == "win32":
            return _appdata() / "Claude" / "skills"
        # linux / other
        return _home() / ".config" / "Claude" / "skills"
    if t is AgentType.CURSOR:
        return _home() / ".cursor" / "skills"
    if t is AgentType.CODEX_CLI:
        return _home() / ".codex" / "skills"
    raise AssertionError(f"unhandled AgentType: {t!r}")  # pragma: no cover


def _detect_marker(t: AgentType) -> pathlib.Path:
    # For all v1 types the install root is the parent of the default skill dir.
    return _default_skill_dir(t).parent
