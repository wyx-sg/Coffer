"""Supported agent types.

The ``AgentType`` enum is the stable identity (persisted value + API contract +
registration whitelist). All *per-type behaviour* — display name, config dir,
detect marker, skill dir — lives in the capability manifest
(:mod:`coffer.domain.agent.descriptor`); these methods delegate to it via a lazy
import so the manifest can reference ``AgentType`` without an import cycle.

Each value covers both the CLI and the app/IDE form of that product, which share
one config directory.
"""

from __future__ import annotations

import pathlib
from enum import StrEnum


class AgentType(StrEnum):
    """Supported agent products."""

    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    CURSOR = "cursor"
    OPENCODE = "opencode"
    OPENCLAW = "openclaw"
    HERMES = "hermes"

    @property
    def display_name(self) -> str:
        from coffer.domain.agent.descriptor import descriptor_for

        return descriptor_for(self).display_name

    def default_name(self) -> str:
        """Stable default resource name when the user does not supply one.

        Mirrors auto-detect naming so a manually-added agent with a blank
        name lands on the same identifier auto-detection would have used:
        underscores become hyphens (e.g. ``claude_code`` -> ``claude-code``).
        """
        return self.value.replace("_", "-")

    def default_skill_dir(self) -> pathlib.Path:
        """Path agents read skills from. Computed per host platform.

        Used when the user does not override the skill dir at registration. The
        path is **not** required to exist — registration validates writability
        separately.
        """
        from coffer.domain.agent.descriptor import descriptor_for

        return descriptor_for(self).default_skill_dir()

    def detect_marker(self) -> pathlib.Path:
        """Path checked during auto-detection (usually the config directory)."""
        from coffer.domain.agent.descriptor import descriptor_for

        return descriptor_for(self).detect_marker()

    def config_dir(self) -> pathlib.Path:
        """Root the config-file allowlist resolves against (``~/.claude``,
        ``~/.codex``, ``~/.cursor``, …)."""
        from coffer.domain.agent.descriptor import descriptor_for

        return descriptor_for(self).default_config_dir()
