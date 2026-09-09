# ADR-037: Rules via runtime SessionStart injection; handoff pull-on-demand

> 中文版: [ADR-037-rules-runtime-injection.zh.md](ADR-037-rules-runtime-injection.zh.md)

**Status**: Accepted
**Date**: 2026-06-22 (revised 2026-09-09, 2026-09-10; see Revision history)
**Deciders**: Yuxing Wu
**Related**: spec `007-memory` (FR-049–FR-052); builds on [ADR-026](ADR-026-memory-via-mcp-not-native-projection.md) (memory via MCP, not native projection); informed by [`docs/research/memory-systems-landscape.md`](../research/memory-systems-landscape.md)

## Context

[ADR-026](ADR-026-memory-via-mcp-not-native-projection.md) removed Coffer's
native-projection layer: Coffer manages memory in its own format and never writes
into, symlinks into, or disables an agent's native memory. It accepted one cost —
the loss of **ambient** loading at session start — and named the remedy
explicitly: a **session-start hook** that injects the current project + global
memory into the agent's context (stdout / context injection, never a file write),
the path `claude-mem` and Letta's `claude-subconscious` take. That was deferred
to "a later slice." This is that slice.

The competitive landscape (`docs/research/memory-systems-landscape.md`) confirms
the field default: shared-memory systems reach a central store at runtime —
queried over MCP/API, or **injected via session hooks** — and never write another
agent's native files. Coffer already ships the MCP floor (`recall`/`remember`)
and a procedural **rules lane** (`rules/rules.md`, FR-036) that is deliberately
**excluded from `recall`** because rules are meant to be **delivered ambiently**,
not discovered by a model that remembers to search. Without an injection
mechanism the rules lane is write-only: the agent never reads it.

One external fact shapes the mechanism: **both Claude Code and Codex have a
SessionStart hook** with the same JSON schema (a top-level `hooks` key; Claude
Code in `~/.claude/settings.json`, Codex in `~/.codex/hooks.json`). The hook
prints
`{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": …}}`,
cannot block the agent, and re-runs on resume/clear/compact. This is exactly an
ambient-context channel that touches no memory or instruction file.

## Decision

**Coffer delivers the rules lane into each managed agent at runtime by installing
a SessionStart hook that injects a rules bundle as CONTEXT ONLY — never a native
file write (ADR-026). The handoff is not injected; it is pulled on demand via
`coffer__resume`.**

Concretely:

- **SessionStart injection (FR-049).** Coffer installs its own entry into the
  agent's top-level `hooks` key (Claude Code `settings.json`; Codex `hooks.json`
  — same JSON schema), recognising only its `coffer-hook` entry by command
  basename and leaving user hooks untouched; install/uninstall is idempotent and
  atomic (`.bak`) and audits `AGENT_HOOK_INSTALLED`/`UNINSTALLED`. On
  SessionStart the `coffer-hook` console script (the agent name baked into its
  args) calls back to the daemon —
  `GET /api/v1/agents/{name}/session-context?cwd=<cwd>` — which assembles the
  bundle: **global rules (always)** + **current-project rules (when the cwd
  resolves to a git project)**, project first. The hook emits it as
  `additionalContext` and exits 0. **It never blocks the agent**: no hook,
  unreachable daemon, timeout, or error → no injection, still exit 0. It re-runs
  on resume/clear/compact.
- **Seeded built-in rules (FR-050).** The bundle always carries two
  Coffer-seeded rules (present even when the rules lanes are empty): (a) call
  `coffer__resume()` to continue prior work, and (b) a soft steer to prefer
  `coffer__write`/`coffer__search` over the agent's native memory. The
  **handoff body itself is NOT injected** — it is pulled on demand via
  `coffer__resume` (FR-025), so the bundle stays small and a stale scene is never
  force-fed into context.
- **Opt-in `disable_native_memory` (FR-052).** A per-agent config, **default
  `false`** (Coffer never touches native memory — the ADR-026 posture). When
  turned on, Coffer writes the agent's native-memory off-switch (Claude Code
  `autoMemoryEnabled=false`; Codex `features.memories=false` +
  `memories.generate_memories=false`) atomically and **restores** it on
  toggle-off/uninstall. This is a **cleanliness option** (avoid a second,
  diverging memory copy), not required for the write guarantee.

## Consequences

**Positive**

- **Ambient rules without touching native files.** Rules load at session start
  for free, exactly the benefit ADR-026 deferred — delivered by the field-default
  mechanism (session-hook context injection) rather than native projection.
- **Not intrusive (still ADR-026).** The injected bundle is context, not a file
  write; the hook entry is reversible and recognises only Coffer's own line.
  Native memory is touched only when the user explicitly opts into
  `disable_native_memory`.
- **Robust by construction.** A hook-less or failed injection never blocks the
  agent (exit 0); the rules bundle works regardless of the
  `disable_native_memory` toggle.

**Negative**

- **Per-agent hook-shape maintenance.** Coffer now tracks each agent's hooks
  config shape and native-memory off-switch — a small surface that can drift as
  upstream formats evolve (mitigated: idempotent, basename-scoped install; both
  agents share the SessionStart JSON schema today).
- **Bundle size ceiling.** `additionalContext` is bounded (~10k chars); a very
  large rules lane could be truncated. Accepted for now (rules are meant to be
  few and durable; the organizer keeps the lane small).

## Alternatives Considered

**Inject the handoff body too (not just a resume rule).** Rejected: a handoff is
a possibly-stale working scene keyed by branch; force-feeding it into every
session's context risks misleading the agent and bloats the bundle. Pull-on-demand
via `coffer__resume` (with a freshness note) is precise and small.

**Render rules into native files (managed block, no symlink).** The softer
projection ADR-026 already rejected — it still writes the user's config files,
the move the field avoids, and still needs per-agent adapters. Session-start
injection achieves the same ambient effect touching no file.

**MCP-only — let the agent `recall` rules on demand.** Rejected for rules
specifically: rules are imperative guidance that must be present before the agent
acts, not retrieved only when it thinks to search. That is why the rules lane is
excluded from `recall` and delivered by injection instead.

## Revision history

- **2026-06-22** — Original decision: SessionStart rules injection, handoff
  pull-on-demand, a Claude-Code-only SessionEnd hook that distilled the
  just-closed session into the journal lane, and the opt-in
  `disable_native_memory` switch.
- **2026-09-09** — Transcript distillation and the journal lane were removed
  from Coffer, so everything this ADR said about SessionEnd distillation (FR-051,
  the Codex latency asymmetry, and the rejected per-turn `Stop` approximation) is
  struck. Nothing now writes memory automatically: an agent records a fact with
  `coffer__remember` and retrieves it with `coffer__recall` (both renamed
  2026-09-10, below). That is simpler and more predictable, and it is a genuine
  trade-off — distillation was working
  (1,320 sessions distilled, 4,669 journal entries) and is being removed because
  the ingest→deliver loop it fed no longer exists end to end, not because it
  failed. **The SessionStart rules-injection decision above still stands
  unchanged** and is what this ADR now records.
- **2026-09-10** — Vocabulary only: `memory` and `knowledge_base` merged into
  one `knowledge` kind, so the tools named above are now `coffer__write` and
  `coffer__search`, and the `rules` lane lives under a knowledge scope
  (`~/.coffer/knowledge/<scope>/rules/`) rather than a memory store. **The
  SessionStart rules-injection decision is unchanged**, and the merge does not
  touch it: rules are still delivered by injection, not by retrieval, and the
  rules lane is still excluded from `coffer__search`.
