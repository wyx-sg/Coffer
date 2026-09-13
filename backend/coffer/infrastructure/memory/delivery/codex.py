"""Codex's session-start-*like* hook adapter.

Codex has no `SessionStart`/`SessionEnd` event. Verified directly against the
installed CLI (`codex-cli 0.139.0`, `@openai/codex`) rather than assumed:
Codex ships no hook-event reference doc, so the event set was read out of its
compiled Rust binary —
`~/.../@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex` —
with `strings`, which turns up exactly five hook-event literals:
`PreToolUse`, `PostToolUse`, `PreCompact`, `Stop`, `UserPromptSubmit`. No
session-start or session-end event exists to install on.

`UserPromptSubmit` is the earliest of those five in a session's lifecycle —
it fires before the first tool call, before any compaction — so it is what
Coffer installs on. It also fires on *every* prompt, not once per session, so
the installed command carries its own once-per-session guard: a lock file
under `${TMPDIR:-/tmp}` keyed by `$PPID` — the invoking Codex process's own
pid, stable for the life of one session, since the hook runs as its direct
child — created on first fire and checked with `[ -e ]` before invoking
Coffer's CLI again. This is a best-effort proxy for "session" in the absence
of any documented session-id hook input on Codex; a session that somehow
shares a pid with an earlier one (extremely unlikely — pids don't reuse
within any realistic session lifetime) would see the guard already tripped
and skip a fire it should have made. Worth revisiting if Codex ever exposes
an actual session id to hooks.

Lives in `~/.codex/hooks.json` (the allowlisted `"hooks"` key —
`domain.agent.allowlists._codex_files`), which already holds skynet-cli's
`UserPromptSubmit`/`PreToolUse`/`Stop` entries on this machine; Coffer's own
entry sits alongside them on the same `UserPromptSubmit` array, never
replacing them (`domain.memory.delivery.install_entry` only ever touches its
own marker-scoped entry).
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.domain.memory import delivery

EVENT = "UserPromptSubmit"
CONFIG_KEY = "hooks"
TIMEOUT_SECONDS = 10

#: `f="..."; [ -e "$f" ] || { : > "$f"; <invocation>; }` — the once-per-
#: session guard, with the invocation spliced in by `command_for`. `: > "$f"`
#: (rather than `touch`) needs no extra binary on `$PATH`.
_GUARD_PREFIX = 'f="${TMPDIR:-/tmp}/.coffer-memory-fired-$PPID"; [ -e "$f" ] || { : > "$f"; '


@dataclass(frozen=True)
class CodexDelivery:
    """`domain.memory.delivery.DeliveryAdapter` for Codex."""

    config_key: str = CONFIG_KEY
    event: str = EVENT

    def command_for(self, agent_key: str) -> str:
        invocation = delivery.context_invocation(agent_key)
        return f": {delivery.MARKER}; {_GUARD_PREFIX}{invocation}; }}"

    def install(self, text: str, agent_key: str) -> str:
        return delivery.install_entry(
            text,
            event=self.event,
            command=self.command_for(agent_key),
            matcher=None,
            timeout=TIMEOUT_SECONDS,
        )

    def remove(self, text: str) -> str:
        return delivery.remove_entry(text, event=self.event)

    def find_command(self, text: str) -> str | None:
        return delivery.find_command(text, event=self.event)


ADAPTER = CodexDelivery()
