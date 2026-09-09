# ADR-013: One Shared Knowledge Store Across Agents

> 中文版: [ADR-013-agent-native-shared-memory.zh.md](./ADR-013-agent-native-shared-memory.zh.md)

**Status**: Partially superseded by [ADR-026](ADR-026-memory-via-mcp-not-native-projection.md) (2026-06-18) — the native-projection half of the decision below was removed; Coffer never writes an agent's own native memory files. The shared-store half stands, and is what this ADR records. Re-expressed in knowledge-layer vocabulary 2026-09-10 (see Revision history).
**Date**: 2026-06-09 (revised 2026-09-10; see Revision history)
**Deciders**: Yuxing Wu
**Related**: spec `007-memory` (the Knowledge Layer spec), [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md), [ADR-007](ADR-007-everything-is-a-resource-kind.md), [ADR-009](ADR-009-cross-platform-skill-delivery.md), [ADR-026](ADR-026-memory-via-mcp-not-native-projection.md), [ADR-035](ADR-035-adopt-native-memory.md), [ADR-037](ADR-037-rules-runtime-injection.md)

## Context

The first memory design (ADR-011) treated each store as a private silo queried
over MCP. In practice a developer runs more than one coding agent (Claude Code,
Codex, …) over the same project. Each agent has its own native memory location —
Claude Code's auto-memory directory, Codex's `memories`, and so on. The same
project fact ("we use squash-merge", "the API base URL is X") then gets written
once per agent and **drifts**: each copy is edited independently and the agents
disagree about the project.

Two forces shape the fix:

1. **A fact about a project is about the project, not about the agent.** It
   should exist once and be visible to every agent working in that project.
2. **Agents load native files ambiently, MCP tools deliberately.** Native files
   (an agent's memory dir, `CLAUDE.md`, `AGENTS.md`) are read into context
   automatically at session start; an MCP tool is only consulted when the agent
   chooses to call it. Whatever we build has to answer for that gap, or a shared
   store is strictly worse than what each agent already does for free.

This sits on top of [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md):
there is one canonical, markdown-files-as-truth substrate underneath. The open
question is how that one store reaches multiple agents without re-introducing
divergent copies.

## Decision

**Coffer holds one shared store, and every agent reads and writes it through
Coffer's own tools. A fact is written once, into Coffer's `knowledge` layer,
and is visible to every agent in that scope. Coffer does not keep a per-agent
copy, and — since [ADR-026](ADR-026-memory-via-mcp-not-native-projection.md) —
does not write into any agent's native memory files either.**

Concrete shape, as it stands today:

- **One resource kind: `knowledge`.** One storage root,
  `~/.coffer/knowledge/<scope>/`, with lanes `knowledge/` (entries an agent
  wrote), `inbox/` (ingested documents), `rules/`, `handoff/`, `superseded/`,
  and a hidden `.raw/` holding the originals of ingested documents. Files are
  truth; SQLite is a rebuildable index over them (ADR-012).
- **Three scopes, read from the resource name.** `global` (cross-project) and
  `project-<ULID>` (resolved from the cwd's git root) both auto-provision on
  first use; any other name is a collection the user created deliberately and
  never auto-provisions, because silently minting a scope from a typo would be
  worse than an error. This is the two-layer scope of the original decision,
  plus a third, deliberate layer for corpora that belong to neither.
- **Canonical format.** An entry is a `.md` file with YAML frontmatter
  (`name`, `description`, `metadata.type`, `origin_session_id`) plus a markdown
  body, under `<scope>/knowledge/`. An ingested document is normalized markdown
  under `<scope>/inbox/`, with its original retained in `<scope>/.raw/` so it
  can be re-converted later. Both lanes index into the same `documents` /
  `chunks` / FTS5 / sqlite-vec substrate, and retrieval spans both.
- **One tool surface, the same for every agent.** Eight MCP tools —
  `coffer__search`, `coffer__grep`, `coffer__read`, `coffer__list`,
  `coffer__write`, `coffer__delete`, `coffer__set_handoff`, `coffer__resume`.
  Each takes an optional `scope`, defaulting to the project scope resolved from
  the shim's reported cwd and falling back to `global`. The caller never has to
  decide which store a fact belongs to before it can search for it. **Adding a
  new agent adds no knowledge-layer code at all** — the tools are already
  agent-agnostic.
- **Ambient delivery without touching the agent's files.** The gap named in
  Context (native loads for free, MCP does not) is closed by
  [ADR-037](ADR-037-rules-runtime-injection.md): the `rules` lane is injected
  into the session at SessionStart, and handoff is pulled on demand via
  `coffer__resume`. Injection is runtime state, so it achieves the ambient
  effect while writing no file the agent owns.
- **Import, never project.** Where an agent has already accumulated its own
  native memory, Coffer reads it and lets the user adopt it **into** the shared
  store once ([ADR-035](ADR-035-adopt-native-memory.md)). The flow is
  one-directional and inbound; nothing flows back out into the agent's files.

**The mechanism this ADR originally chose was different, and was removed.** It
projected the canonical store *outward* into each agent's native location — an
`AgentMemoryAdapter` per agent with a `projection_mode` of
`SYMLINK | RENDER | NONE`, symlinking the canonical directory into Claude
Code's auto-memory path, rendering a marker-fenced managed block into Codex
config files, and **disabling each agent's own native memory** so the canonical
store stayed the only writer.
[ADR-026](ADR-026-memory-via-mcp-not-native-projection.md) withdrew all of it
in 2026-06-18: writing and disabling another tool's config is intrusive, the
per-agent adapters had to track upstream formats that keep moving, and the
ambient-loading benefit that justified the cost is obtainable by injection
instead. What survives, and what this ADR is now read for, is the shared-store
decision itself.

## Consequences

**Positive**

- **One fact, every agent, no drift.** A fact is written once and every agent
  in that scope reads the same file. The dual/triple-copy divergence problem is
  structurally removed, and it is removed by there being one copy rather than
  by keeping several in sync.
- **No per-agent knowledge code.** Because the tool surface is agent-agnostic
  and Coffer never touches an agent's own files, onboarding a new agent costs
  nothing in the knowledge layer — in contrast to the per-agent adapter the
  original mechanism required.
- **Clean layering.** Knowledge (L2) never authors an agent's config (L1). The
  boundary the original decision maintained through an adapter is now
  maintained by simply not crossing it.
- **The caller does not classify.** With one kind and one set of tools, an
  agent no longer has to decide whether something is "memory" or "knowledge"
  before it can store or find it.

**Negative**

- **Retrieval is deliberate, not automatic.** An agent sees a fact when it
  calls `coffer__search` (or when the rules lane is injected). Only the rules
  and handoff paths are ambient; ordinary entries are not pushed into context.
  This is the cost of not writing the agent's files, and it is accepted.
- **The user must adopt existing native memory explicitly.** Facts already
  sitting in an agent's own store do not migrate on their own; ADR-035's import
  is a user action.
- **Coffer's tools are the only write path.** An agent that cannot speak MCP
  cannot contribute to the shared store.

## Alternatives Considered

**A silo per agent, as in ADR-011.** Rejected: it is the drift this ADR
exists to remove.

**Native projection per agent (the original mechanism here).** Symlink where
the format already matches, a managed block where it does not, and disable the
agent's own native memory so copies cannot diverge. Superseded by ADR-026:
Coffer would be mutating and disabling another tool's configuration, and every
supported agent would owe a hand-maintained adapter tracking a format that
changes upstream.

**Render into each agent's own memory format, bidirectional.** Project the
canonical store *into* each agent's proprietary format and parse it *back* on
edit, so every agent edits natively and changes flow both ways. Rejected:
round-tripping a proprietary, evolving agent memory format losslessly is
industry-unsolved and inherently lossy.

**Fold knowledge into the agent-workspace config (let it write `CLAUDE.md`
directly).** Rejected on layering grounds: it collapses the L1 (config) / L2
(knowledge) boundary. Knowledge stays agent-agnostic.

**Two kinds, one substrate — a `memory` face and a `knowledge_base` face.**
This is how the store was actually built, and it was merged away on 2026-09-10
(see [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md)'s revision history).
The substrate was shared from the start; only the facade was two, and it made
callers guess which face a fact belonged to. Rejected in retrospect: sharing a
store across agents is the point, and a second face over the same store is a
second thing to keep in sync for no gain.

## Revision history

- **2026-06-09** — Initial decision: one canonical per-fact-markdown memory
  store, shared across agents by a hybrid of MCP read/write plus per-agent
  native projection (`SYMLINK | RENDER | NONE`), with each projected agent's own
  native memory disabled. Scope was two-layer: global + per-project.
- **2026-06-18** — [ADR-026](ADR-026-memory-via-mcp-not-native-projection.md)
  removed the projection half: Coffer never writes or disables an agent's native
  memory files. The shared-store half was unaffected.
- **2026-09-10** — Re-expressed for the knowledge-layer merge. The store this
  ADR shares across agents is now the single `knowledge` kind (`memory` and
  `knowledge_base` merged); store names became the three scopes; the twelve
  `coffer__*` memory/KB tools became eight. The decision — one shared store, not
  one per agent — is unchanged; only the vocabulary it is written in has moved.
