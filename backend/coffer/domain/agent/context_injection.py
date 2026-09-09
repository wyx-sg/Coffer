"""How Coffer injects its session context (rules + memory) into one agent.

One mechanism exists (FR-043): the agent execs the ``coffer-hook`` binary at
session start and reads its stdout, which carries the FR-044 rules bundle
assembled by ``GET /api/v1/agents/{agent}/session-context``. Coffer's part is to
write that command into the agent's hooks JSON file; the agent's runtime owns
the rest.

The on-disk entry is Claude Code's matcher-group shape — a top-level ``hooks``
object keyed by PascalCase event name, each event holding matcher groups::

    {"hooks": {"SessionStart": [
        {"matcher": "startup|resume",
         "hooks": [{"type": "command", "command": "..."}]}]}}

Codex shares that shape, so the on-disk key for an event is simply
:attr:`HookEvent.value` and no per-agent dialect exists. ``coffer-hook`` always
prints the matching ``hookSpecificOutput.additionalContext`` envelope.

The registry once carried products with no shell hook at all, which needed two
further mechanisms (a dropped in-process JS plugin; a marker block rendered into
the instructions file). Those products are gone, and so are those mechanisms —
see "Why only these two" in spec 004.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from coffer.domain.agent.config_files import ConfigFileFormat

#: The top-level container key in the agent's hooks JSON.
HOOK_CONTAINER_KEY = "hooks"


class HookEvent(StrEnum):
    """The lifecycle events Coffer hooks into.

    The value IS the on-disk key: both supported products spell events in
    Claude Code's PascalCase.
    """

    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"


@dataclass(frozen=True)
class ContextInjectionSpec:
    """Where Coffer writes its ``coffer-hook`` entry for one agent.

    ``config_key`` names the allowlisted hooks file (resolved against the
    agent's config dir by the application layer): ``settings`` for Claude Code,
    ``hooks`` for Codex. ``events`` is the set of lifecycle events an entry is
    installed for — Codex has no usable session-end event, so it installs
    ``SESSION_START`` only.
    """

    config_key: str
    format: ConfigFileFormat
    events: tuple[HookEvent, ...] = ()
