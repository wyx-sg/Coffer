"""How Coffer injects its session context (rules + memory) into one agent.

Supersedes the old ``hook_injection`` module, which modelled exactly one delivery
mechanism — "write a shell command into a JSON config file" — and therefore
declared an absent facet for every agent whose upstream does context injection
some other way. Three mechanisms exist in the wild:

``SHELL_COMMAND``
    The agent execs ``coffer-hook`` at session start and reads its stdout.
    Claude Code, Codex, and Cursor all work this way, but not in the same
    *shape*: see :class:`HookFlavor`.

``PLUGIN_DROP``
    The agent has no shell hook, only in-process JS/TS callbacks (opencode,
    openclaw). Coffer drops a thin plugin that spawns the same ``coffer-hook``
    binary. The on-disk shape differs per :class:`PluginFlavor`: one flat file
    (opencode) vs a package directory plus an explicit enable flag (openclaw).

``INSTRUCTIONS_BLOCK``
    The agent has no working hook at all (Hermes: its ``on_session_start`` /
    ``pre_llm_call`` hooks are documented but never invoked upstream — see
    NousResearch/hermes-agent#2817, closed as not planned). Coffer renders the
    same payload into a marker block in the agent's instructions file
    (transforms in ``instructions_block.py``), refreshed before each
    Coffer-driven turn.

All three modes are implemented (FR-043 / FR-047 / FR-048) and share one
payload source: the daemon's ``GET /api/v1/agents/{agent}/session-context``
endpoint. Only the last mile — who fetches it and in what envelope it reaches
the model — varies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from coffer.domain.agent.config_files import ConfigFileFormat

#: The top-level container key is ``hooks`` for every agent that has one.
HOOK_CONTAINER_KEY = "hooks"


class InjectionMode(StrEnum):
    """How Coffer's session context reaches the agent's model."""

    #: The agent runs ``coffer-hook`` and reads its stdout (Claude Code, Codex,
    #: Cursor).
    SHELL_COMMAND = "shell_command"
    #: Coffer drops an in-process plugin that spawns ``coffer-hook`` (opencode,
    #: openclaw — no shell hook; rendering in ``plugin_drop.py`` /
    #: ``plugin_drop_openclaw.py`` per :class:`PluginFlavor`).
    PLUGIN_DROP = "plugin_drop"
    #: Coffer renders the payload into a marker block in the instructions file
    #: (Hermes — no working upstream hook exists).
    INSTRUCTIONS_BLOCK = "instructions_block"


class HookEvent(StrEnum):
    """The lifecycle events Coffer hooks into, as Coffer names them.

    These are Coffer's *canonical* names. The on-disk key an agent expects is
    derived per :class:`HookFlavor` via :func:`event_key` — Cursor spells the
    same event ``sessionStart``.
    """

    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"


class HookFlavor(StrEnum):
    """The dialect of an agent's ``hooks`` JSON — entry shape, event-key
    spelling, and the stdout envelope ``coffer-hook`` must print.

    ``CLAUDE`` (Claude Code, Codex)
        Event keys are PascalCase. Each event holds matcher groups::

            {"hooks": {"SessionStart": [
                {"matcher": "startup|resume",
                 "hooks": [{"type": "command", "command": "..."}]}]}}

        stdout envelope: ``{"hookSpecificOutput": {"hookEventName": ...,
        "additionalContext": ...}}``.

    ``CURSOR``
        Event keys are camelCase. Each event holds flat command entries, and the
        document carries a top-level ``version``::

            {"version": 1, "hooks": {"sessionStart": [{"command": "..."}]}}

        stdout envelope: ``{"additional_context": ...}``.
    """

    CLAUDE = "claude"
    CURSOR = "cursor"


class PluginFlavor(StrEnum):
    """The on-disk shape of a ``PLUGIN_DROP`` agent's plugin — what Coffer must
    write for the agent's runtime to load it.

    ``OPENCODE``
        One flat ``coffer-session-context.js`` file in the auto-loaded
        ``plugin/`` directory. Loading is implicit (presence == loaded).

    ``OPENCLAW``
        A PACKAGE DIRECTORY ``extensions/coffer-session-context/`` holding
        ``package.json`` + ``openclaw.plugin.json`` + ``index.js``
        (``definePluginEntry`` + a ``before_prompt_build`` handler), AND —
        non-bundled plugins are fail-closed — an explicit
        ``plugins.entries.coffer-session-context.enabled: true`` flag in
        ``openclaw.json`` (the spec's ``plugin_enable_config_key``). Rendering
        + config transforms live in ``plugin_drop_openclaw.py``.
    """

    OPENCODE = "opencode"
    OPENCLAW = "openclaw"


#: Cursor's ``hooks.json`` carries a schema version at the top level. Coffer sets
#: it when creating the file and never rewrites an existing value.
CURSOR_SCHEMA_VERSION = 1

_EVENT_KEYS: dict[HookFlavor, dict[HookEvent, str]] = {
    HookFlavor.CLAUDE: {
        HookEvent.SESSION_START: "SessionStart",
        HookEvent.SESSION_END: "SessionEnd",
    },
    HookFlavor.CURSOR: {
        HookEvent.SESSION_START: "sessionStart",
        HookEvent.SESSION_END: "sessionEnd",
    },
}


def event_key(flavor: HookFlavor, event: HookEvent) -> str:
    """The key this agent's hooks file uses for ``event``."""
    return _EVENT_KEYS[flavor][event]


@dataclass(frozen=True)
class ContextInjectionSpec:
    """Where and how Coffer injects session context for one agent.

    ``config_key`` names the allowlisted config file the mode writes into
    (resolved against the agent's config dir by the application layer) — the
    hooks file for ``SHELL_COMMAND``, the instructions file for
    ``INSTRUCTIONS_BLOCK``. ``events`` is the set of lifecycle events Coffer
    installs an entry for — Codex and Cursor have no usable session-end event,
    so they install ``SESSION_START`` only; an ``INSTRUCTIONS_BLOCK`` agent has
    no events at all (the block is not event-driven), so it declares ``()``.
    ``flavor`` is meaningful for ``SHELL_COMMAND`` only; ``plugin_flavor``
    (and, for a flavor whose plugins are fail-closed, ``plugin_enable_config_key``
    — the allowlisted config file carrying the enable flag) for ``PLUGIN_DROP``
    only.
    """

    mode: InjectionMode
    config_key: str
    format: ConfigFileFormat
    events: tuple[HookEvent, ...] = ()
    flavor: HookFlavor = HookFlavor.CLAUDE
    container_key: str = HOOK_CONTAINER_KEY
    plugin_flavor: PluginFlavor = PluginFlavor.OPENCODE
    plugin_enable_config_key: str | None = None
