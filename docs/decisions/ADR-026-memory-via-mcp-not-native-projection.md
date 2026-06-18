# ADR-026: Memory via MCP, not native projection (supersedes ADR-013)

> 中文版: [ADR-026-memory-via-mcp-not-native-projection.zh.md](ADR-026-memory-via-mcp-not-native-projection.zh.md)

**Status**: Accepted
**Date**: 2026-06-18
**Deciders**: Yuxing Wu
**Related**: spec `007-memory`, supersedes [ADR-013](ADR-013-agent-native-shared-memory.md); builds on [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md); informed by [`docs/research/memory-systems-landscape.md`](../research/memory-systems-landscape.md)

## Context

[ADR-013](ADR-013-agent-native-shared-memory.md) made Coffer's one canonical
memory store reach multiple agents through **native projection**: symlink the
canonical per-project memory dir into Claude Code's auto-memory location, render
a marker-fenced managed block into Codex / OpenCode / OpenClaw / Hermes config
files, and **disable each agent's own native memory** so no second copy could
diverge. MCP `recall`/`remember` were the universal floor; projection was the
extra layer that made memory load "ambiently" at session start.

A competitive survey (`docs/research/memory-systems-landscape.md`) put that
choice in context and surfaced a **yellow flag**: of every shared-memory system
examined (mem0, Letta, Zep/Graphiti, the MCP memory server, claude-mem,
agentmemory), **none writes into another agent's native memory files**. They use
a central store reached at runtime — query over MCP/API, or inject context via
session hooks. Letta's own Claude Code integration (`claude-subconscious`)
**deliberately never writes `CLAUDE.md`** and even strips leftover blocks.
Multi-target native fan-out was Coffer's genuinely novel contribution — and also
the one thing the rest of the field had considered and **avoided**.

Three forces made the projection layer a net negative in practice:

1. **Legibility.** Adopting Claude Code's auto-memory format (so the Claude
   projection could be a symlink) meant per-project stores were keyed and
   surfaced as opaque `project-<ULID>` directories. Users could not tell which
   project a store belonged to (the trigger for this reversal).
2. **Intrusiveness.** Projection writes into and disables the user's own agent
   config — exactly the move the industry avoids. It is hard to reverse cleanly,
   carries cross-platform symlink caveats, and needs a per-agent adapter that
   tracks each agent's evolving native-memory shape.
3. **Cost vs. benefit.** The only benefit projection bought over plain MCP was
   _ambient_ loading at session start. That can be recovered without touching
   native files — by injecting the memory index into context via a session-start
   hook (the path claude-mem and `claude-subconscious` take), which is a smaller,
   non-intrusive mechanism that we can add per agent later.

## Decision

**Coffer manages memory in its own per-fact-markdown format and never operates
on an agent's native memory files. Agents read and write memory only through the
MCP gateway tools (`coffer__recall` / `remember` / `update_memory` / `forget` /
`list_memory`). The native-projection layer is removed entirely.**

Concretely:

- **Removed:** the `AgentMemoryAdapter` protocol + `ProjectionEngine` + per-agent
  adapters (SYMLINK/RENDER/NONE), the projection FS adapter, the
  `memory_projection_bindings` table (dropped by migration `0023`), the
  projection REST endpoints (`/memory_stores/{name}/projections…`), the
  native-memory discovery/take-over route, the `coffer memory bind/unbind/projections`
  CLI commands, and the `memory_projected` audit event. Coffer no longer disables
  any agent's native memory.
- **Kept (unchanged):** files-as-truth per-fact markdown + regenerated
  `MEMORY.md` ([ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md)); the
  two-layer scope (global + per-project, resolved from the MCP shim's cwd →
  git-root); the shared retrieval engine (grep / FTS5 keyword / sqlite-vec
  vector) with lazy reindex-on-read; transcript distillation (ADR-020); and full
  human curation via UI/CLI.
- **Legibility (FR-017a):** because Coffer owns its format, a per-project store is
  presented by a human-readable identity derived from its `project_root` (the
  directory basename + path) instead of the `project-<ULID>` name.
- **Ambient loading (deferred follow-up):** a session-start hook may inject the
  current project + high-priority global memory _index_ into the agent's context
  (stdout / context injection, never a file write), with bodies fetched on demand
  via `recall`. Until then MCP recall is the access path. This is intentionally a
  later slice, not part of this change.

## Consequences

**Positive**

- **Not intrusive.** Coffer never writes, symlinks into, or disables an agent's
  own memory. The agent's native memory is its own; Coffer's is Coffer's,
  reached via tools. This is the industry-default posture.
- **Legible + curatable.** Project stores read by name/path; no opaque ULID
  directories forced by an adopted native format.
- **Much less code, fewer moving parts.** Drops ~1.7k LOC of projection engine /
  adapters / FS / persistence / routes / wiring and a DB table; one fewer
  per-agent surface to track as upstream formats change.
- **No divergence-disabling.** We no longer flip an agent's config to turn off
  its native memory — a reversible-but-invasive step ADR-013 itself flagged.

**Negative**

- **Loses ambient auto-load until the injection hook lands.** With MCP-only
  access an agent sees memory only when it calls `recall`; native files load into
  context for free at session start. This was ADR-013's core reason for
  projection. Mitigation: the session-start injection hook (above) restores
  ambient presence without writing native files; it is the next slice.
- **Abandons the novelty claim.** Multi-target native fan-out was Coffer's unique
  contribution per the research; the central-store-plus-tool-access model is
  proven but unremarkable. Accepted deliberately: simplicity, legibility, and
  non-intrusiveness outweigh novelty here.

## Alternatives Considered

**Keep native projection (ADR-013).** Rejected: the legibility and
intrusiveness costs are real and recurring, and the one benefit (ambient load)
is recoverable by runtime injection. The novelty is not worth writing into and
disabling users' agent config.

**Render the memory index into native files (managed block only, no symlink, no
disabling native memory).** A softer projection. Rejected: still writes into the
user's config files (the move the field avoids), still needs per-agent adapters,
and a session-start context injection achieves the same ambient effect without
touching any file.

**MCP-only with no ambient mechanism at all.** Viable and simplest, but memory
that loads only when the model remembers to call `recall` is underused.
Runtime injection via a session hook is the planned, non-intrusive remedy — so
MCP-only is the floor we ship now, with injection as the funded follow-up.
