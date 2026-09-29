"""Coffer's own session-start hook: the installed command, the ceiling on
what it prints, the adapter Protocol, and the shape of an install/status view.
The marker and the JSON text transform live in `domain.memory.hook_entries`
and are re-exported here.

Pure — no filesystem access; the application layer reads an agent's own
settings file through the same allowlisted machinery every other config-file
edit in this codebase uses (`domain.agent.config_files` + the
`ConfigFileStorePort`), calls the functions here to produce new text, and
writes it back atomically. See `application.memory.delivery.DeliveryService`.

**A hook is not memory.** Installing this writes one entry into an agent's
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
    InstalledHook,
    MalformedDeliveryConfig,
    find_command,
    find_installed,
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


def context_invocation(
    agent_uid: str, *, cli: str = "coffer", hook_event: str | None = None
) -> str:
    """The bare CLI call Coffer wants running at session start.

    ``cli`` is the **absolute path** of the ``coffer`` binary whenever the
    composition root can find one. A hook runs under whatever shell the agent
    starts, and that shell need not read the user's rc files: Codex runs its
    hooks under ``/bin/zsh`` with a ``PATH`` that does not include
    ``~/.coffer/bin``, so a bare ``coffer`` there is "command not found" and the
    hook delivers nothing. The bare name is only the fallback for a build that
    cannot locate its own CLI.

    ``hook_event``, when given, asks the CLI to wrap the text as that event's
    JSON ``hookSpecificOutput.additionalContext`` rather than print it plain.

    The agent is named by its **uid**, not by its registry name (ADR
    resource-identity-is-an-immutable-uid). An installed hook is a string
    sitting in somebody else's settings file for months; a name is a label the
    user may edit in that time, and the hook would then report an agent that no
    longer answers to anything. There is no name fallback on the reading side
    either — one spelling, and it is the one that cannot change.

    `--cwd` reads the shell's own `$PWD` at fire time, not a value baked in
    at install time: both agents run the hook with the session's working
    directory as its own, and that directory is only known when the hook
    actually runs.
    """
    call = f'{shlex.quote(cli)} memory context --agent-uid {shlex.quote(agent_uid)} --cwd "$PWD"'
    if hook_event is not None:
        call += f" --hook-event {shlex.quote(hook_event)}"
    return call


def hook_command(agent_uid: str, *, cli: str = "coffer", hook_event: str | None = None) -> str:
    """The exact command string Coffer installs for `agent_uid`.

    Marker-scoped: every adapter's installed command starts with the same
    `": {MARKER};"` prefix, so it is recognised identically regardless of what
    follows. That is also what makes a changed command costless for an
    already-installed hook: detection never reads the arguments, so a
    reinstall replaces the entry in place and an old one is found and removed
    exactly as before.
    """
    return f": {MARKER}; {context_invocation(agent_uid, cli=cli, hook_event=hook_event)}"


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
    #: `resource_id`: a surface has to render something a person recognises,
    #: and looking the name up again would be a second question with a second
    #: chance to disagree. It is never matched on.
    agent_name: str
    installed: bool
    #: What is installed, when `installed`; otherwise what `install()` would
    #: write, so a caller can show it before acting.
    command: str
    #: The hook event this agent's adapter installs on (`"SessionStart"`,
    #: `"UserPromptSubmit"`, ...).
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
        """The hook event this adapter installs on."""
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
        """Coffer's entry on whichever event it sits — an older build's may sit
        on an event this build no longer installs on — or `None`."""
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
    "DELIVERY_CEILING_BYTES",
    "HOOKS_KEY",
    "MARKER",
    "DeliveryAdapter",
    "DeliveryStatus",
    "DeliveryUnsupported",
    "HookTrust",
    "InstalledHook",
    "MalformedDeliveryConfig",
    "context_invocation",
    "find_command",
    "find_installed",
    "hook_command",
    "install_entry",
    "is_installed",
    "is_marked",
    "remove_entry",
]
