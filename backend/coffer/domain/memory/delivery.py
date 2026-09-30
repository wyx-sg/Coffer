"""Coffer's own memory hook: the four entries it installs (session start, each
prompt, before and after a shell command), the command they run, the ceiling on
what session start prints, the adapter Protocol, and the shape of an
install/status view. The marker and the JSON text transform live in
`domain.memory.hook_entries` and are re-exported here.

Pure — no filesystem access; the application layer reads an agent's own
settings file through the same allowlisted machinery every other config-file
edit in this codebase uses (`domain.agent.config_files` + the
`ConfigFileStorePort`), calls the functions here to produce new text, and
writes it back atomically. See `application.memory.delivery.DeliveryService`.

**A hook is not memory.** Installing this writes Coffer's entries into an agent's
*settings* file — Claude Code's `settings.json`, Codex's `hooks.json` — the
same file that already carries a developer's `env`, `permissions`, and every
other hook a tool like skynet-cli wired up. It is how the developer told
their tool to run *something* at a lifecycle event; it carries no facts of
its own. Coffer's memory layer reads an agent's *native memory* (Claude
Code's per-fact Markdown, Codex's `MEMORY.md`/profile) read-only and never
writes it (`docs/decisions/aggregate-agent-memory-never-write-it.md`). This
module writes a hook, which is a different kind of file entirely, and only
ever on an explicit `DeliveryService.install()` call — never as a side effect
of registering an agent, aggregating memory, or serving a turn (spec memory
"Install delivery hooks explicitly and removably").

The previous session-context injection layer shipped, was never installed on
the maintainer's own machine, and nothing said so for two months (spec memory
"Audit every delivery fire", the ADR's
"Delivery is a push ... installed on purpose"). The fix is
that a fire is *recorded*: `DeliveryService.record_fired()`, called by
whatever serves the context, writes one audit entry per fire. So "installed"
and "has ever run" stay two different facts, read in the two places each
belongs — this status for the first, the audit log for the second.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Protocol

from coffer.domain.error_base import CofferError
from coffer.domain.hook_trust import HookTrust
from coffer.domain.memory.hook_entries import (
    HOOKS_KEY,
    MARKER,
    EntrySpec,
    InstalledHook,
    MalformedDeliveryConfig,
    find_all_installed,
    find_command,
    find_installed,
    install_entries,
    install_entry,
    is_installed,
    is_marked,
    remove_entry,
)


class DeliveryUnsupported(CofferError):  # noqa: N818
    """`agent_type` has no session-start-like hook adapter.

    Only the two agent types Coffer reads native memory from today (Claude
    Code, Codex — spec memory "Read Claude Code and Codex memory with their
    search terms") have one; a third agent type earns an
    adapter under `infrastructure.memory.delivery` before this stops raising
    for it.
    """

    code = "MEMORY_DELIVERY_UNSUPPORTED"

    def __init__(self, agent_type: str) -> None:
        super().__init__(f"agent type {agent_type!r} has no memory-delivery hook adapter")
        self.agent_type = agent_type


#: The ceiling on one delivered payload, in UTF-8 bytes of text. Both agents
#: that run Coffer's hook cut an injection that is larger than this, and both
#: cuts lose the lines that matter:
#:
#: * **Claude Code** keeps a hook's output inline up to about 10,000
#:   characters. Past that it saves the output to a file and shows the model a
#:   ~2 KB preview, which is the newest few `global` lines and nothing about
#:   the repository.
#: * **Codex** keeps `additionalContext` up to 2,500 tokens, which it counts as
#:   UTF-8 bytes / 4, so 10,000 bytes. Past that it keeps the head and the tail
#:   and cuts the middle.
#:
#: A byte count satisfies both: a text of N UTF-8 bytes is never more than N
#: characters. 9,500 leaves room for the line an agent adds around the output.
#: See spec memory "Bound delivery and prefer the current repository".
DELIVERY_CEILING_BYTES = 9500


#: The four moments memory reaches a session (ADR
#: memory-reaches-a-session-at-prompt-time-and-before-a-known-trap): the index at
#: session start, retrieval per prompt, the guard before a shell command, and
#: the error context after one. Both supported agents run all four and read the
#: same JSON from each.
SESSION_START = "SessionStart"
USER_PROMPT_SUBMIT = "UserPromptSubmit"
PRE_TOOL_USE = "PreToolUse"
POST_TOOL_USE = "PostToolUse"
DELIVERY_EVENTS = (SESSION_START, USER_PROMPT_SUBMIT, PRE_TOOL_USE, POST_TOOL_USE)
#: The moments a channel turn carries itself: Coffer puts the index in its
#: system prompt and the notes its prompt names after the prompt (spec memory
#: "Deliver to channel turns through the system prompt"). The hook answers
#: nothing on these in a process Coffer spawned for a channel turn
#: (``coffer.domain.channel_turn``), so each moment has one owner; the guard
#: and the error context stay the hook's, since the turn does neither.
CHANNEL_TURN_EVENTS = (SESSION_START, USER_PROMPT_SUBMIT)

#: Every source that starts a session, in both agents' vocabulary.
SESSION_MATCHER = "startup|resume|clear|compact"
#: The shell tool, by the name both agents hand a hook (``tool_name``).
SHELL_TOOL_MATCHER = "Bash"

#: Generous enough that a slow first call never blocks the session from
#: starting; short enough that a hung daemon does not hang the terminal.
SESSION_TIMEOUT_SECONDS = 10
#: A prompt or a command waits at most this long for Coffer; the CLI itself
#: gives up sooner and prints nothing (fail open).
TURN_TIMEOUT_SECONDS = 5


def hook_invocation(agent_uid: str, *, cli: str = "coffer") -> str:
    """The CLI call every one of Coffer's four entries runs.

    One command for every event: it reads the hook's own JSON from stdin, whose
    ``hook_event_name`` says which moment this is, and prints the JSON that
    moment answers with. ``--cwd "$PWD"`` is the fallback for an event whose
    input carries no ``cwd``; it reads the shell's own ``$PWD`` at fire time,
    because the session's working directory is only known when the hook runs.

    ``cli`` is the **absolute path** of the ``coffer`` binary whenever the
    composition root can find one. A hook runs under whatever shell the agent
    starts, and that shell need not read the user's rc files: Codex runs its
    hooks under ``/bin/zsh`` with a ``PATH`` that does not include
    ``~/.coffer/bin``, so a bare ``coffer`` there is "command not found" and the
    hook delivers nothing. The bare name is only the fallback for a build that
    cannot locate its own CLI.

    The agent is named by its **uid**, not by its registry name (ADR
    resource-identity-is-an-immutable-uid). An installed hook is a string
    sitting in somebody else's settings file for months; a name is a label the
    user may edit in that time, and the hook would then report an agent that no
    longer answers to anything.
    """
    return f'{shlex.quote(cli)} memory hook --agent-uid {shlex.quote(agent_uid)} --cwd "$PWD"'


def entry_command(agent_uid: str, *, cli: str = "coffer") -> str:
    """The exact command string Coffer installs on each event, marker first.

    Marker-scoped: every adapter's installed command starts with the same
    ``": {MARKER};"`` prefix, so it is recognised identically regardless of what
    follows. Detection never reads the arguments, so a reinstall replaces the
    entry in place and an old one is found and removed exactly as before.
    """
    return f": {MARKER}; {hook_invocation(agent_uid, cli=cli)}"


def delivery_entries(agent_uid: str, *, cli: str = "coffer") -> tuple[EntrySpec, ...]:
    """The four entries one agent carries: the same command on every event,
    the shell tool's events matched on the shell tool alone."""
    command = entry_command(agent_uid, cli=cli)
    return (
        EntrySpec(SESSION_START, command, SESSION_MATCHER, SESSION_TIMEOUT_SECONDS),
        EntrySpec(USER_PROMPT_SUBMIT, command, None, TURN_TIMEOUT_SECONDS),
        EntrySpec(PRE_TOOL_USE, command, SHELL_TOOL_MATCHER, TURN_TIMEOUT_SECONDS),
        EntrySpec(POST_TOOL_USE, command, SHELL_TOOL_MATCHER, TURN_TIMEOUT_SECONDS),
    )


def events_label(events: tuple[str, ...] | list[str]) -> str:
    """The set of events a hook sits on, as one comparable string."""
    return ",".join(sorted(set(events)))


def commands_label(commands: tuple[str, ...] | list[str]) -> str:
    """The commands Coffer's entries carry, as one comparable string: the
    command itself when every entry agrees, otherwise every distinct one."""
    distinct = sorted(set(commands))
    return distinct[0] if len(distinct) == 1 else " | ".join(distinct)


@dataclass(frozen=True)
class DeliveryStatus:
    """Whether Coffer's hook is installed for one agent.

    Deliberately *only* that. Whether the hook has fired is not a property of
    the agent but a stream of events, and it is reported as one: an audit
    entry per fire ("Audit every delivery fire"), read on the Activity surface
    beside every other
    thing that happened.
    """

    #: Which agent, by identity — what the installed command carries and what
    #: a caller addresses this status by.
    agent_uid: str
    #: The agent's label at the moment the status was read, carried beside the
    #: uid for the same reason an audit row carries `resource_name` beside
    #: `resource_uid`: a surface has to render something a person recognises,
    #: and looking the name up again would be a second question with a second
    #: chance to disagree. It is never matched on.
    agent_name: str
    installed: bool
    #: What is installed, when `installed`; otherwise what `install()` would
    #: write, so a caller can show it before acting.
    command: str
    #: The hook events this agent's adapter installs on, comma-joined
    #: (``PostToolUse,PreToolUse,SessionStart,UserPromptSubmit``).
    event: str


class DeliveryAdapter(Protocol):
    """What one agent's hook adapter provides.

    `application.memory.delivery.DeliveryService` composes against this
    Protocol, never against a specific agent module — a third agent is one
    more adapter under `infrastructure.memory.delivery`, not a change to the
    service. It is the delivery-hook entry of the agent's projection facet
    (ADR agent-mechanisms-are-optional-facets-on-the-descriptor), bound to the
    agent it declares at the composition root.
    """

    @property
    def agent_type(self) -> str:
        """The agent type's value this adapter serves (``claude_code``)."""
        ...

    @property
    def config_key(self) -> str:
        """The `ConfigFileSpec` key (`domain.agent.config_files`) holding
        this agent's hooks — `"settings"` for Claude Code, `"hooks"` for
        Codex. A read-only property so a frozen-dataclass adapter satisfies
        this Protocol (a plain attribute would require it to be settable)."""
        ...

    @property
    def event(self) -> str:
        """The hook events this adapter installs on, as :func:`events_label`
        spells them."""
        ...

    def command_for(self, agent_uid: str) -> str:
        """What `install()` would write for `agent_uid` — installed or not."""
        ...

    def install(self, text: str, agent_uid: str) -> str:
        """Return new config text with Coffer's entry for `agent_uid`
        inserted or replaced in place. Idempotent; every other entry,
        including one on the same event another tool wrote, is preserved."""
        ...

    def remove(self, text: str) -> str:
        """Return new config text with ONLY Coffer's entry removed."""
        ...

    def find_command(self, text: str) -> str | None:
        """The installed command, or `None` if Coffer has no entry."""
        ...

    def find(self, text: str) -> InstalledHook | None:
        """Coffer's entry on whichever event it sits, or `None`."""
        ...

    def find_all(self, text: str) -> list[InstalledHook]:
        """Every Coffer entry in the file, on every event."""
        ...

    def is_coffer_command(self, command: str) -> bool:
        """Whether a hook command found in the agent's config is Coffer's own
        (by the marker, never by the arguments)."""
        ...

    @property
    def trust_config_key(self) -> str | None:
        """The `ConfigFileSpec` key of the file where the agent records which
        hooks the user has trusted, or `None` when it runs every hook it finds."""
        ...

    def trust(self, hooks_text: str, trust_text: str | None, hooks_path: str) -> HookTrust:
        """Whether the agent will run Coffer's entry in `hooks_text` (the file
        at `hooks_path`), judged from its trust record `trust_text`. Reads;
        never writes. `NOT_REQUIRED` for an agent with no review step."""
        ...


__all__ = [
    "CHANNEL_TURN_EVENTS",
    "DELIVERY_CEILING_BYTES",
    "DELIVERY_EVENTS",
    "HOOKS_KEY",
    "MARKER",
    "POST_TOOL_USE",
    "PRE_TOOL_USE",
    "SESSION_MATCHER",
    "SESSION_START",
    "SESSION_TIMEOUT_SECONDS",
    "SHELL_TOOL_MATCHER",
    "TURN_TIMEOUT_SECONDS",
    "USER_PROMPT_SUBMIT",
    "DeliveryAdapter",
    "DeliveryStatus",
    "DeliveryUnsupported",
    "EntrySpec",
    "HookTrust",
    "InstalledHook",
    "MalformedDeliveryConfig",
    "commands_label",
    "delivery_entries",
    "entry_command",
    "events_label",
    "find_all_installed",
    "find_command",
    "find_installed",
    "hook_invocation",
    "install_entries",
    "install_entry",
    "is_installed",
    "is_marked",
    "remove_entry",
]
