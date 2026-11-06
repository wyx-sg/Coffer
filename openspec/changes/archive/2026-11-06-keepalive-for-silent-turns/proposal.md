## Why

The four-hour wait for background sub-agents (ADR
`a-claude-code-turn-waits-for-its-background-sub-agents`) was still cut short by
the turn runner's 300-second idle watchdog whenever the agent produced no event
for five minutes. Codex has the same exposure: a long command or a sub-agent
thread emits nothing until it finishes. The owner chose a keepalive over raising
the default timeout; the options are argued in ADR
`adapters-signal-liveness-with-a-keepalive-event`.

## What Changes

- New internal event `TurnProgress`: resets the idle watchdog, never emitted to
  subscribers.
- Claude: sub-agent task messages and a held result emit it.
- Codex: notifications from other threads, and own notifications that map to
  nothing, emit it.

## Impact

- `domain/chat/events`, `turn_runner`, `claude_sdk_mapping`, `codex_agent`; chat
  spec; architecture docs (en, zh).
