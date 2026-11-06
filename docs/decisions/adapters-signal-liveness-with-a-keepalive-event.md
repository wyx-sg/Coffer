# Adapters Signal Liveness With a Keepalive Event

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: [A Claude Code Turn Waits for Its Background Sub-Agents](a-claude-code-turn-waits-for-its-background-sub-agents.md), spec chat "idle watchdog"

## Context

The turn runner cancels a turn that produces no event for 300 seconds
(`COFFER_TURN_IDLE_TIMEOUT_SECONDS`) so a wedged agent cannot hold a conversation
forever. Two legitimate cases are silent for longer: a Claude Code turn waiting
up to four hours for a background sub-agent, and a Codex turn running a long
command or a sub-agent thread on the same app-server. The watchdog cut both off.

Comparable products: Claude Code's terminal UI has no idle cutoff, the user
interrupts; the Agent SDK leaves timeouts to the caller; CI runners (GitHub
Actions) time out on total duration, not silence, and commands may emit
heartbeat output.

## Options Considered

- **A. Keepalive event.** Adapters emit an internal `TurnProgress` when they see
  signs of life that are not user-visible; the runner resets the window and drops
  it. Pros: the watchdog still catches a truly wedged agent; no config change.
  Cons: a completely silent sub-agent (no progress messages) for five minutes is
  still cancelled; one more event type.
- **B. Raise the default timeout to four hours.** Pros: one-line change. Cons: a
  wedged agent now blocks the conversation for four hours; the owner would need
  to lower it again for the common case.
- **C. Disable the watchdog while a background task runs.** Pros: precise.
  Cons: the runner would need agent-specific knowledge; a hung sub-agent is
  never caught.

## Decision

Option A. Claude emits it for sub-agent task messages and a held result; Codex
for other threads' notifications and own notifications that map to nothing.

## Consequences

- Waiting on background work no longer trips the watchdog while the agent
  reports progress.
- Not verified against a real Codex or Claude Code process; a fully silent
  sub-agent is still cancelled after the idle window.
