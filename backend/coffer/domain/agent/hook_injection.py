"""How Coffer installs its ``coffer-hook`` lifecycle hooks into an agent (Slice 6).

Claude Code and Codex share the same hook-config shape: a top-level ``hooks``
object keyed by event name (``SessionStart`` / ``SessionEnd``), each holding a
list of ``{ "matcher": ..., "hooks": [ {"type": "command", "command": ...} ] }``
entries. Both store it as JSON (Claude ``settings.json``; Codex ``hooks.json``).

The descriptor (spec 004) carries one :class:`HookInjectionSpec` per agent that
manages hooks — Claude Code installs both SessionStart and SessionEnd; Codex has
no session-end event, so it installs SessionStart only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from coffer.domain.agent.config_files import ConfigFileFormat

#: The top-level container key is always ``hooks`` for every current agent.
HOOK_CONTAINER_KEY = "hooks"


class HookEvent(StrEnum):
    """Agent session-lifecycle events Coffer hooks into.

    The values are the external hook-event names (the keys under the ``hooks``
    object and the ``hook_event_name`` field on the stdin payload).
    """

    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"


@dataclass(frozen=True)
class HookInjectionSpec:
    """Where and which lifecycle hooks Coffer installs for one agent.

    ``config_key`` names the allowlisted config file that holds the hooks
    (resolved against the agent's config dir by the application layer). The
    container key is always ``hooks``. ``events`` is the set of lifecycle
    events Coffer installs a ``coffer-hook`` entry for.
    """

    config_key: str
    format: ConfigFileFormat
    events: tuple[HookEvent, ...]
    container_key: str = HOOK_CONTAINER_KEY
