"""Where an agent runs Coffer's one hook: the session-start hook that hands a
session the project's memories (spec memory "Hand a session its project's
memories at start"; ADR keep-memory-in-one-place-agents-write-themselves).

Coffer installs exactly one hook of its own into an agent. It fires when a
session starts and prints the current project's memories, which the agent adds
to the session's context. Claude Code keeps hooks under ``hooks`` in
``settings.json``; Codex in ``hooks.json``. Both use one shape::

    {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "…"}]}]}}

and both add a SessionStart hook's plain standard output to the session as
context, so one renderer serves both. An agent whose hooks take another shape
or another output gets its own :class:`SessionHookSpec` values.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The words that make a hook command Coffer's: ``<coffer> memory session-start``.
HOOK_SUBCOMMAND = ("memory", "session-start")


@dataclass(frozen=True)
class SessionHookSpec:
    """How Coffer's session-start hook lands in one agent."""

    #: The allowlist key of the file that holds the agent's own hooks.
    config_key: str
    #: The event the hook is registered under.
    event: str = "SessionStart"


__all__ = ["HOOK_SUBCOMMAND", "SessionHookSpec"]
