"""Coffer's own session-start-like hook: the marker, the installed command,
the JSON text transform, and the shape of an install/status view.

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
FR-054).

The previous session-context injection layer shipped, was never installed on
the maintainer's own machine, and nothing said so for two months (spec memory
FR-055, the ADR's "Delivery is a push ... installed on purpose"). The fix is
that a fire is *recorded*: `DeliveryService.record_fired()`, called by
whatever serves the context, writes one audit entry per fire. So "installed"
and "has ever run" stay two different facts, read in the two places each
belongs — this status for the first, the audit log for the second.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from typing import Any, Protocol

from coffer.domain.error_base import CofferError

#: Marks every hook entry Coffer installs. Embedded as the argument to a
#: leading no-op `:` shell command so it survives verbatim at the very start
#: of the installed command string regardless of what an adapter wraps around
#: it (Codex's once-per-session guard) or what CLI binary name a future
#: packaging change picks — detection never depends on `argv[0]`.
MARKER = "coffer-memory"

#: The one top-level key both supported formats keep their hook entries
#: under (Claude Code's `settings.json`, Codex's `hooks.json`): an object
#: keyed by event name, each value a list of matcher groups.
HOOKS_KEY = "hooks"


class MalformedDeliveryConfig(CofferError):  # noqa: N818
    """The agent's settings/hooks file is not a JSON object Coffer can edit.

    Raised instead of silently clobbering content Coffer cannot parse — the
    caller (`application.memory.delivery`) re-raises this with the file's
    path attached, since a domain function never sees a path, only text.
    """

    code = "MEMORY_DELIVERY_CONFIG_INVALID"


class DeliveryUnsupported(CofferError):  # noqa: N818
    """`agent_type` has no session-start-like hook adapter.

    Only the two agent types Coffer reads native memory from today (Claude
    Code, Codex — spec memory FR-004) have one; a third agent type earns an
    adapter under `infrastructure.memory.delivery` before this stops raising
    for it.
    """

    code = "MEMORY_DELIVERY_UNSUPPORTED"

    def __init__(self, agent_type: str) -> None:
        super().__init__(f"agent type {agent_type!r} has no memory-delivery hook adapter")
        self.agent_type = agent_type


def context_invocation(agent_key: str) -> str:
    """The bare CLI call Coffer wants running at session start.

    `--cwd` reads the shell's own `$PWD` at fire time, not a value baked in
    at install time: the session's working directory is only known when the
    hook actually runs (as the *hook's own* process — a child of the
    session), never when it is installed.
    """
    return f'coffer memory context --agent {shlex.quote(agent_key)} --cwd "$PWD"'


def hook_command(agent_key: str) -> str:
    """The exact command string Coffer installs for `agent_key`.

    Marker-scoped: an adapter that wraps this further (Codex's once-per-
    session guard) keeps the same `": {MARKER};"` prefix, so every adapter's
    installed command is recognised identically regardless of what follows.
    """
    return f": {MARKER}; {context_invocation(agent_key)}"


@dataclass(frozen=True)
class DeliveryStatus:
    """Whether Coffer's hook is installed for one agent.

    Deliberately *only* that. Whether the hook has fired is not a property of
    the agent but a stream of events, and it is reported as one: an audit
    entry per fire (FR-055), read on the Activity surface beside every other
    thing that happened.
    """

    agent: str
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
    service.
    """

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

    def command_for(self, agent_key: str) -> str:
        """What `install()` would write for `agent_key` — installed or not."""
        ...

    def install(self, text: str, agent_key: str) -> str:
        """Return new config text with Coffer's entry for `agent_key`
        inserted or replaced in place. Idempotent; every other entry,
        including one on the same event another tool wrote, is preserved."""
        ...

    def remove(self, text: str) -> str:
        """Return new config text with ONLY Coffer's entry removed."""
        ...

    def find_command(self, text: str) -> str | None:
        """The installed command, or `None` if Coffer has no entry."""
        ...


def _parse(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError as e:
        raise MalformedDeliveryConfig(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise MalformedDeliveryConfig("top-level value must be a JSON object")
    return data


def _dump(data: dict[str, Any]) -> str:
    # ensure_ascii=False: a settings file may hold non-ASCII content
    # (project paths, plugin names) elsewhere; escaping it on every install
    # would needlessly rewrite unrelated bytes. Mirrors mcp_install.py.
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _is_coffer_leaf(leaf: Any) -> bool:
    if not isinstance(leaf, dict):
        return False
    cmd = leaf.get("command")
    return isinstance(cmd, str) and cmd.startswith(f": {MARKER}")


def _is_coffer_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    leaves = entry.get("hooks")
    if not isinstance(leaves, list):
        return False
    return any(_is_coffer_leaf(leaf) for leaf in leaves)


def install_entry(
    text: str,
    *,
    event: str,
    command: str,
    matcher: str | None,
    timeout: int | None = None,
) -> str:
    """Return `text` with Coffer's hook entry for `event` inserted/replaced.

    Idempotent: a prior Coffer entry for `event` is dropped and replaced with
    a fresh one carrying `command`; every other entry — another event
    entirely, or a foreign hook on this SAME event — is left untouched.
    """
    data = _parse(text)
    hooks = data.get(HOOKS_KEY)
    if not isinstance(hooks, dict):
        hooks = {}
        data[HOOKS_KEY] = hooks
    entries = hooks.get(event)
    kept = [e for e in entries if not _is_coffer_entry(e)] if isinstance(entries, list) else []
    leaf: dict[str, Any] = {"type": "command", "command": command}
    if timeout is not None:
        leaf["timeout"] = timeout
    new_entry: dict[str, Any] = {"hooks": [leaf]}
    if matcher is not None:
        new_entry = {"matcher": matcher, "hooks": [leaf]}
    kept.append(new_entry)
    hooks[event] = kept
    return _dump(data)


def remove_entry(text: str, *, event: str) -> str:
    """Return `text` with ONLY Coffer's entry for `event` removed.

    A foreign hook on the same event, every other event, and every unrelated
    top-level key are left intact. A now-empty event array is dropped
    cleanly, and so is an empty top-level `hooks` object — mirrors the
    removed injection layer's own cleanup behaviour.
    """
    data = _parse(text)
    hooks = data.get(HOOKS_KEY)
    if not isinstance(hooks, dict):
        return _dump(data)
    entries = hooks.get(event)
    if isinstance(entries, list):
        kept = [e for e in entries if not _is_coffer_entry(e)]
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        del data[HOOKS_KEY]
    return _dump(data)


def find_command(text: str, *, event: str) -> str | None:
    """The command of Coffer's entry for `event`, or `None` if absent."""
    data = _parse(text)
    hooks = data.get(HOOKS_KEY)
    if not isinstance(hooks, dict):
        return None
    entries = hooks.get(event)
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not _is_coffer_entry(entry):
            continue
        for leaf in entry.get("hooks", []):
            if _is_coffer_leaf(leaf):
                return str(leaf.get("command"))
    return None


def is_installed(text: str, *, event: str) -> bool:
    """Whether Coffer's entry for `event` is present in `text`."""
    return find_command(text, event=event) is not None
