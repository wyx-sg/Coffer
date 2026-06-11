# ADR-013: Agent-Native Shared Memory Projection

> 中文版: [ADR-013-agent-native-shared-memory.zh.md](./ADR-013-agent-native-shared-memory.zh.md)

**Status**: Accepted
**Date**: 2026-06-09
**Deciders**: Yuxing Wu
**Related**: spec `007-memory`, [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md), [ADR-007](ADR-007-everything-is-a-resource-kind.md), [ADR-009](ADR-009-cross-platform-skill-delivery.md)

## Context

The first `memory` design (ADR-011) treated each memory store as a private
silo queried over MCP. In practice a developer runs more than one coding agent
(Claude Code, Codex, …) over the same project. Each agent has its own native
memory location — Claude Code's auto-memory directory, Codex's `memories`, etc.
The same project fact ("we use squash-merge", "the API base URL is X") then gets
written once per agent and **drifts**: each copy is edited independently and the
agents disagree about the project.

Two forces shape the fix:

1. **A fact about a project is about the project, not about the agent.** It
   should exist once and be visible to every agent working in that project.
2. **Agents load native memory ambiently, MCP memory deliberately.** Native
   files (Claude's memory dir, `CLAUDE.md`, `AGENTS.md`) are read into context
   automatically at session start; MCP tools are only consulted when the agent
   chooses to call `recall`. Dropping native loading would make memory
   strictly worse than what agents already do for free.

This sits on top of [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md): there
is now a single canonical, per-fact-markdown memory store with files as truth.
The open question is how that one store reaches multiple agents without
re-introducing divergent copies.

## Decision

**Keep one canonical per-fact-markdown memory store and share it across agents
through a hybrid mechanism: MCP read/write for every agent, plus native
projection per agent via an `AgentMemoryAdapter` whose `projection_mode` is
`SYMLINK | RENDER | NONE`. When an agent is projected, disable that agent's own
native memory so the canonical store is the only writer and copies cannot
diverge. Memory scope is two-layer: global (cross-project) + per-project.**

Concrete shape:

- **Canonical format.** Per-fact `.md` files with YAML frontmatter
  (`name`, `description`, `metadata.type`, `origin_session_id`) + a markdown
  body, plus a regenerated `MEMORY.md` index. This is Claude Code's auto-memory
  format, adopted as canonical _precisely so_ the Claude projection can be a
  native directory symlink (no rendering, no lossy round-trip).
- **Two-layer scope.** Global facts live in the `WORKSPACE_GLOBAL_PROJECT_ID`
  sentinel store (the existing F0x sentinel — not a new one); per-project facts
  live in `projects/<project-ulid>/`. `remember(scope=project)` resolves to the
  project store via the MCP shim's reported cwd → git-root; `recall` defaults to
  both layers.
- **Projection matrix.**

  |                   | Claude Code                                                                                                                        | Codex                                                                               |
  | ----------------- | ---------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
  | **Project layer** | `SYMLINK` the canonical dir → `~/.claude/projects/<slug>/memory/` (native, bidirectional, keep auto-memory ON — it _is_ canonical) | `RENDER` a marker-fenced block into `<project>/AGENTS.md`; disable Codex `memories` |
  | **Global layer**  | `RENDER` block into `~/.claude/CLAUDE.md`                                                                                          | `RENDER` block into `~/.codex/AGENTS.md`                                            |

- **Managed block** for `RENDER` mode (idempotent, re-rendered on memory change):

  ```
  <!-- coffer:memory:start (managed, do not edit) -->
  … rendered facts …
  <!-- coffer:memory:end -->
  ```

- **`AgentMemoryAdapter`** lives with the agent driver (the agent layer that
  already owns L1 config files — `CLAUDE.md` / `AGENTS.md` / rules), **not** with
  the memory kind:

  ```
  memory_location(project) -> path | None
  projection_mode          -> SYMLINK | RENDER | NONE
  disable_native_memory(agent_config)   # only when native memory would be a separate copy
  render(facts) -> bytes                # RENDER mode
  ```

  The projection engine dispatches on `projection_mode`; the adapter performs all
  file mutations. The memory substrate only provides canonical files + rendered
  markdown, keeping it agent-agnostic and the L1/L2 boundary clean (memory never
  authors config; the agent's own adapter injects the managed block).
  **Adding a new agent = one adapter, no core change** ([ADR-009](ADR-009-cross-platform-skill-delivery.md)'s
  per-agent-delivery shape recurs here).

- **Disable native memory on projection.** Where a `RENDER` agent has its own
  writable native memory (Codex `memories`), it is turned off so the only writer
  is the canonical store. `SYMLINK` agents keep native memory ON because the
  symlinked directory _is_ the canonical store (same inode → no divergence).
- **Establish lazily** at session start per reported cwd. If an agent's native
  memory dir already holds real files, **merge into canonical first, then**
  replace with a symlink — never silently overwrite.

## Consequences

**Positive**

- **One fact, every agent, no drift.** A project fact is written once and read
  by Claude (live symlink) and Codex (re-rendered block) and any future agent.
  The dual/triple-copy divergence problem is structurally removed.
- **Ambient native loading preserved.** Agents still read memory from their
  native locations at session start; MCP `recall` is additive, not the only
  path. Memory is strictly better than per-agent native memory, not a sidegrade.
- **Clean layering.** Memory (L2) never authors config (L1); the agent's adapter
  — which already owns the agent's L1 files — is the single component that
  touches them. Adding an agent does not touch the memory kind.
- **Cheap freshness.** Symlinks are live (same inode); managed blocks re-render
  idempotently on memory change; `recall` does a lazy reindex-on-read of the
  small fact dir, so Claude's symlink edits are immediately visible to all agents
  with no filesystem watcher.

**Negative**

- **Per-agent adapter maintenance.** Each agent's native memory shape, config
  flag to disable it, and file location must be tracked and can change upstream.
  Mitigated by the one-adapter-per-agent confinement.
- **`RENDER` is one-directional.** For `RENDER` agents, edits flow canonical →
  native only; the agent cannot edit memory by editing its `AGENTS.md` block (it
  would be overwritten on the next render). Those agents write via MCP instead.
  This is a deliberate trade to avoid lossy round-tripping (see Alternatives).
- **Disabling native memory is intrusive.** Coffer flips an agent's own config to
  turn off its native memory. This must be explicit, reversible, and never
  silent — and we must migrate any pre-existing native facts into canonical
  before doing it.
- **Symlink portability.** Directory symlinks have the same cross-platform
  caveats as [ADR-009](ADR-009-cross-platform-skill-delivery.md)'s skill
  delivery (Windows junction / copy-fallback considerations) and must follow the
  same strategy.

## Alternatives Considered

**MCP-only (no native projection), as in ADR-011.** Viable and simplest: one
canonical store, every agent reads/writes via `recall`/`remember`. Rejected as
the _sole_ mechanism because it loses ambient native loading — the agent only
sees memory if it remembers to call the tool, whereas native files load into
context for free at session start. We keep MCP as the universal floor and add
projection on top.

**Render-per-agent in each agent's own memory format, bidirectional.** Project
the canonical store _into_ each agent's proprietary memory format and parse it
_back_ on edit, so every agent edits memory natively and changes flow both ways.
Rejected: round-tripping a proprietary, evolving agent memory format losslessly
is industry-unsolved and inherently lossy. We sidestep it — symlink where the
format already matches (Claude), one-directional managed block elsewhere, MCP for
writes — rather than build a fragile bidirectional translator.

**Fold memory into the agent-workspace config (let memory write `CLAUDE.md`
directly).** Rejected on layering grounds: it collapses the L1 (config) / L2
(knowledge) boundary. Memory stays agent-agnostic; only the agent's own adapter
injects a marker-fenced block, which is reversible and clearly demarcated.

## Prior art & novelty

Managed-block injection into agent config files is established prior art:
**Next.js** ships a `<!-- BEGIN:nextjs-agent-rules -->` block into `AGENTS.md`,
and **claude-mem** injects a `<claude-mem-context>` block into `CLAUDE.md`.
Coffer reuses this proven pattern for `RENDER` mode.

What is **novel** is multi-agent native projection of accumulated memory. Every
canonical-memory system surveyed (mem0/OpenMemory, Letta, Zep, Cognee, the MCP
memory server, MemPalace) is MCP-centric; the only native-file projectors
(claude-mem, agentmemory) are Claude-only, single-target. Coffer's fan-out of
one canonical store into _multiple_ agents' native locations (symlink where the
format matches, managed block where it does not, MCP everywhere) is unclaimed in
OSS as of mid-2026. The risk of a novel mechanism is mitigated by the
adapter confinement and by MCP remaining the universal fallback if a given
agent's projection is not yet implemented.
