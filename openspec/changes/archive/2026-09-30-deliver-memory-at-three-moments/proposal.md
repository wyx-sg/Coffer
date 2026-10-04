# Deliver memory at three moments

## Why

Memory reached a session only at its start, as a bounded index. On the
107-case eval set built from the maintainer's own transcripts that avoided the
first-attempt mistake in 1 of 18 live runs; prompt-time retrieval together with
a once-per-session guard on authored triggers avoided it in 18 of 18, at about
320 injected tokens a run. [Memory Reaches a Session at Three Moments](../../../docs/decisions/memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md)
decides the design; this change implements it.

## What changes

- **Four hook entries per agent.** Claude Code and Codex each get Coffer's
  entry on `SessionStart`, `UserPromptSubmit`, and `PreToolUse` / `PostToolUse`
  on the shell, all running one command, `coffer memory hook`, which reads the
  event from stdin and prints the JSON both agents read. The reconciler moves an
  older single entry to the four, and Codex's approval is read for every entry.
- **Prompt-time retrieval.** Each substantive prompt brings in the top three
  notes of the session's repository and `global` above a relevance floor,
  ranked with BM25 over an in-memory index, at most 1.5 KB, never a note the
  session was already given.
- **A guard before a known trap.** Authored triggers in `vault/memory-triggers/`
  deny the first matching shell command of a session once, with the note as the
  reason, and add the note after a command whose output shows a known error.
  Vault sync carries them to the user's other machines.
  Distil may propose a trigger; only a person arms one. REST
  `/api/v1/memory/triggers` and `coffer memory trigger list|add|arm|disarm|delete`.
- **Fail open.** A hook that cannot reach the daemon in time prints nothing and
  exits 0; a trivial prompt or an unmatched command never contacts the daemon.
- **Delivery views for the Memory page.** `GET /api/v1/memory/deliveries`
  (per agent over seven days: fires by moment, the last one, distinct notes read
  from the paths its tool calls named) and
  `GET /api/v1/memory/partitions/{uid}/delivered` (each agent's exact
  session-start text); `coffer memory delivered [<partition>]`.
- **Audit.** Every delivering fire is a `memory_delivery_fired` event naming its
  moment, session and notes; trigger acts are `memory_trigger_*` events.

## Capabilities

- `memory` — new requirements for retrieval, the guard, triggers, failing open,
  wording, the delivery views and per-turn rules; modified hook installation,
  repair, audit, the REST/CLI family and the transcript rule.
- `vault-sync` — the round mirrors and applies `memory-triggers/` beside
  `knowledge/` and `skills/`.
- `agent-registry` (and its `codex`, `claude-code` children) — Coffer's hook is
  four entries in the hooks listing, and Codex trust covers every entry.
