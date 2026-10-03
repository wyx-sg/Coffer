"""Codex's memory hook adapter.

Codex (0.155 and later) runs `SessionStart` and `UserPromptSubmit` hooks with
the same stdin shape as Claude Code, and its hook input carries the session's
id. Coffer installs one entry on each, both running the same
`coffer memory hook` command. Anything once-per-session is keyed on that
`session_id`, never on a process id: under Codex Desktop and the IDE hosts
every session of one `codex app-server` shares a parent pid, so a key on
`$PPID` would let only the first session of each app-server fire.

Three things make the hooks actually run and actually arrive:

* **JSON output.** Every event prints `{"hookSpecificOutput": {...}}`: Codex
  hands `additionalContext` to the model as a developer message. Past 2,500
  tokens (UTF-8 bytes / 4) it keeps only the head and the tail of a context, so
  every payload is bounded under that (`domain.memory.delivery.DELIVERY_CEILING_BYTES`).
* **An absolute CLI path.** Codex runs hooks under `/bin/zsh` without the
  user's rc files, so `~/.coffer/bin` is not on the hook's `PATH`.
* **Trust.** Codex runs a non-managed hook only once the user has reviewed it, entry by entry.
  It records trust in `config.toml` under
  `[hooks.state."<hooks.json path>:<event>:<group>:<handler>"].trusted_hash`,
  against a hash of the hook's normalised definition, and silently skips a
  hook whose hash has no match. Every change to Coffer's command therefore
  needs the user's approval again (`/hooks` in Codex). Coffer never writes that
  record: it is Codex's own review gate, and spec agent-registry/codex "Leave
  Codex's internal-state tables untouched" keeps `[hooks.state.*]`
  byte-identical across every write. Coffer computes the same hash, reads the
  record, and reports the result (:meth:`CodexDelivery.trust`).

Lives in `~/.codex/hooks.json` (the allowlisted `"hooks"` key —
`domain.agent.allowlists._codex_files`), beside whatever other tools wired up;
Coffer's own entry sits alongside them on the same `SessionStart` array, never
replacing them (`domain.memory.delivery.install_entries` only ever touches its
own marker-scoped entries).
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from typing import Any

from coffer.domain.hook_trust import HookTrust
from coffer.domain.memory import delivery

EVENT = delivery.events_label(delivery.DELIVERY_EVENTS)
CONFIG_KEY = "hooks"
#: Where Codex keeps its trust records.
TRUST_CONFIG_KEY = "config"

#: Codex's defaults, which its normalisation writes into the hashed identity:
#: `codex-rs/hooks/src/engine/discovery.rs` (`normalize_command_hook`) and
#: `codex-rs/hooks/src/output_spill.rs` (`DEFAULT_HOOK_OUTPUT_TOKEN_LIMIT`).
_DEFAULT_TIMEOUT_SECONDS = 600
_DEFAULT_ADDITIONAL_CONTEXT_LIMIT = 2500

#: Events whose matcher Codex ignores, so it is left out of the hash
#: (`codex-rs/hooks/src/events/common.rs`, `matcher_pattern_for_event`).
_MATCHERLESS_EVENTS = frozenset({"UserPromptSubmit", "Stop", "Interrupt"})


def _event_key_label(event: str) -> str:
    """`SessionStart` -> `session_start`, as Codex's `hook_event_key_label` spells it."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", event).lower()


def trust_key(hooks_path: str, hook: delivery.InstalledHook) -> str:
    """The `[hooks.state]` key Codex records trust for this entry under."""
    return f"{hooks_path}:{_event_key_label(hook.event)}:{hook.group_index}:{hook.handler_index}"


def current_hash(hook: delivery.InstalledHook) -> str:
    """The hash Codex computes for this entry (`hook_hash` + `version_for_toml`).

    Codex hashes a normalised identity rather than the file's text: the event's
    snake-case label, the matcher (for events that read one), and the one
    handler with its defaults filled in and its unset options left out. It
    serialises that to JSON with sorted keys and no whitespace, and prefixes
    the SHA-256 with ``sha256:``. Reproduced here so Coffer can tell whether
    Codex will run the hook without starting Codex.
    """
    leaf = hook.handler
    handler: dict[str, Any] = {
        "type": "command",
        "command": hook.command,
        "timeout": max(int(leaf.get("timeout") or _DEFAULT_TIMEOUT_SECONDS), 1),
        "async": bool(leaf.get("async", False)),
    }
    status = leaf.get("statusMessage")
    if isinstance(status, str):
        handler["statusMessage"] = status
    limit = leaf.get("additionalContextLimit")
    if isinstance(limit, int) and limit != _DEFAULT_ADDITIONAL_CONTEXT_LIMIT:
        handler["additionalContextLimit"] = limit
    identity: dict[str, Any] = {"event_name": _event_key_label(hook.event), "hooks": [handler]}
    if hook.matcher is not None and hook.event not in _MATCHERLESS_EVENTS:
        identity["matcher"] = hook.matcher
    serialized = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CodexDelivery:
    """`domain.memory.delivery.DeliveryAdapter` for Codex."""

    #: The agent this adapter serves, by its type value (the memory kind
    #: declares it as a value; it may not import the agent kind's modules).
    agent_type: str = "codex"
    config_key: str = CONFIG_KEY
    event: str = EVENT
    #: The `coffer` CLI the hook runs — an absolute path, resolved by the
    #: composition root (see `domain.memory.delivery.hook_invocation`).
    cli: str = "coffer"
    trust_config_key: str | None = TRUST_CONFIG_KEY

    def command_for(self, agent_uid: str) -> str:
        return delivery.entry_command(agent_uid, cli=self.cli)

    def install(self, text: str, agent_uid: str) -> str:
        return delivery.install_entries(text, delivery.delivery_entries(agent_uid, cli=self.cli))

    def remove(self, text: str) -> str:
        return delivery.remove_entry(text)

    def find_command(self, text: str) -> str | None:
        return delivery.find_command(text)

    def find(self, text: str) -> delivery.InstalledHook | None:
        return delivery.find_installed(text)

    def find_all(self, text: str) -> list[delivery.InstalledHook]:
        return delivery.find_all_installed(text)

    def is_coffer_command(self, command: str) -> bool:
        return delivery.is_marked(command)

    def trust(self, hooks_text: str, trust_text: str | None, hooks_path: str) -> HookTrust:
        """Whether Codex will run **every** one of Coffer's entries.

        Codex records trust per entry, so two entries are two approvals; the
        answer is the first entry's that is not trusted, in file order, and
        ``TRUSTED`` only when all are.
        """
        try:
            hooks = delivery.find_all_installed(hooks_text)
        except delivery.MalformedDeliveryConfig:
            return HookTrust.UNKNOWN
        if not hooks:
            return HookTrust.UNTRUSTED
        try:
            config = tomllib.loads(trust_text or "")
        except tomllib.TOMLDecodeError:
            return HookTrust.UNKNOWN
        hooks_table = config.get("hooks")
        states = hooks_table.get("state") if isinstance(hooks_table, dict) else None
        for hook in hooks:
            verdict = _entry_trust(states, hooks_path, hook)
            if verdict is not HookTrust.TRUSTED:
                return verdict
        return HookTrust.TRUSTED


def _entry_trust(states: Any, hooks_path: str, hook: delivery.InstalledHook) -> HookTrust:
    state = states.get(trust_key(hooks_path, hook)) if isinstance(states, dict) else None
    if not isinstance(state, dict):
        return HookTrust.UNTRUSTED
    if state.get("enabled") is False:
        return HookTrust.DISABLED
    trusted = state.get("trusted_hash")
    if not isinstance(trusted, str):
        return HookTrust.UNTRUSTED
    if trusted == current_hash(hook):
        return HookTrust.TRUSTED
    return HookTrust.MODIFIED


ADAPTER = CodexDelivery()

__all__ = ["ADAPTER", "CodexDelivery", "current_hash", "trust_key"]
