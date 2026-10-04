"""Supported agent types.

The ``AgentType`` enum is the stable identity (persisted value + API contract +
registration whitelist). All *per-type behaviour* — display name, config dir,
skill dir — lives in the capability manifest
(:mod:`coffer.domain.agent.descriptor`); these methods delegate to it via a lazy
import so the manifest can reference ``AgentType`` without an import cycle.

Each value covers both the CLI and the app/IDE form of that product, which share
one config directory.
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping
from enum import StrEnum
from typing import Any


class AgentType(StrEnum):
    """Supported agent products."""

    CLAUDE_CODE = "claude_code"
    CODEX = "codex"

    @property
    def display_name(self) -> str:
        from coffer.domain.agent.descriptor import descriptor_for

        return descriptor_for(self).display_name

    def default_name(self) -> str:
        """The name of this type's one agent: underscores become hyphens
        (``claude_code`` -> ``claude-code``). There is no other name an agent
        may carry (spec agent-registry "Keep one agent per type, named by it")."""
        return self.value.replace("_", "-")

    def default_skill_dir(self) -> pathlib.Path:
        """Path agents read skills from. Computed per host platform.

        Used when the user does not override the skill dir at registration. The
        path is **not** required to exist — registration validates writability
        separately.
        """
        from coffer.domain.agent.descriptor import descriptor_for

        return descriptor_for(self).default_skill_dir()

    def config_dir(self) -> pathlib.Path:
        """Root the config-file allowlist resolves against (``~/.claude``,
        ``~/.codex``)."""
        from coffer.domain.agent.descriptor import descriptor_for

        return descriptor_for(self).default_config_dir()


def parse_agent_ref(ref: str) -> AgentType | None:
    """The type ``ref`` spells — its name (``claude-code``) or its value
    (``claude_code``) — or ``None`` when it spells none, e.g. a uid.

    An agent is one per type and named by it (spec agent-registry "Keep one
    agent per type, named by it"), so a type is enough to address it.
    """
    for agent_type in AgentType:
        if ref in (agent_type.value, agent_type.default_name()):
            return agent_type
    return None


def agent_display_name(config: Mapping[str, Any], fallback: str) -> str:
    """The product name to show for an agent row's ``config`` ("Claude Code"),
    or ``fallback`` — its name — when the config names no supported type.

    An agent carries no title (spec agent-registry "Keep one agent per type,
    named by it"), so a surface that labels one for a person reads its type.
    """
    agent_type = config.get("type")
    try:
        return AgentType(agent_type).display_name if isinstance(agent_type, str) else fallback
    except ValueError:
        return fallback
