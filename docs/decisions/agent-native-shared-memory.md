# One Shared Knowledge Store: One Shared Knowledge Store Across Agents

> 中文版: [agent-native-shared-memory.zh.md](./agent-native-shared-memory.zh.md)

**Status**: Partially superseded by [Memory via MCP](memory-via-mcp-not-native-projection.md) (2026-06-18) — the native-projection half of the decision below was removed; Coffer never writes an agent's own native memory files. The shared-store half stands, and is what this ADR records. Re-expressed in knowledge-layer vocabulary 2026-09-10 and narrowed to two lanes 2026-09-11. The store's SHAPE — lanes, scopes, the tool list — is superseded by [Knowledge Is Plain Files](knowledge-is-plain-files.md) (2026-09-12); read the body below for the decision, not for the layout (see Revision history).
**Date**: 2026-06-09 (revised 2026-09-11; see Revision history)
**Deciders**: Yuxing Wu
**Related**: spec `knowledge` (the Knowledge Layer spec), [Files as Truth](files-as-truth-sqlite-retrieval.md), [Everything Is a Resource Kind](everything-is-a-resource-kind.md), [Cross-Platform Skill Delivery](cross-platform-skill-delivery.md), [Memory via MCP](memory-via-mcp-not-native-projection.md)

## Context

The first memory design (on the mem0 memory engine) treated each store as a private silo queried
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

This sits on top of [Files as Truth](files-as-truth-sqlite-retrieval.md):
there is one canonical, markdown-files-as-truth substrate underneath. The open
question is how that one store reaches multiple agents without re-introducing
divergent copies.

## Decision

**Coffer holds one shared store, and every agent reads and writes it through
Coffer's own tools. A fact is written once, into Coffer's `knowledge` layer,
and is visible to every agent in that scope. Coffer does not keep a per-agent
copy, and — since [Memory via MCP](memory-via-mcp-not-native-projection.md) —
does not write into any agent's native memory files either.**

Concrete shape, as it stands today:

- **One resource kind: `knowledge`.** One storage root,
  `~/.coffer/knowledge/<scope>/`, with two lanes — `notes/` (what an agent or
  the user wrote) and `docs/` (uploaded documents, normalized to markdown) —
  plus a hidden `.history/` holding pre-rewrite copies and a hidden
  `.raw/` holding the uploaded originals. Files are truth; SQLite is a
  rebuildable index over them (Files as Truth).
- **Three scopes, read from the resource name.** `global` (cross-project) and
  `project-<ULID>` (resolved from the cwd's git root) both auto-provision on
  first use; any other name is a collection the user created deliberately and
  never auto-provisions, because silently minting a scope from a typo would be
  worse than an error. This is the two-layer scope of the original decision,
  plus a third, deliberate layer for corpora that belong to neither.
- **Canonical format.** A note is a `.md` file with YAML frontmatter
  (`name`, `description`, `metadata.type`, `origin_session_id`) plus a markdown
  body, under `<scope>/notes/`. An uploaded document is normalized markdown
  under `<scope>/docs/`, with its original retained in `<scope>/.raw/` so it
  can be re-converted later. Both lanes index into the same `documents` /
  `chunks` / FTS5 / sqlite-vec substrate, and retrieval spans both.
- **One tool surface, the same for every agent.** Six MCP tools —
  `coffer__search`, `coffer__grep`, `coffer__read`, `coffer__list`,
  `coffer__write`, `coffer__delete`. Each takes an optional `scope`, defaulting
  to the project scope resolved from the shim's reported cwd and falling back to
  `global`. The caller never has to
  decide which store a fact belongs to before it can search for it. **Adding a
  new agent adds no knowledge-layer code at all** — the tools are already
  agent-agnostic.
- **Ambient delivery without touching the agent's files.** _Withdrawn
  2026-09-10._ The gap named in Context — native memory loads for free, MCP does
  not — was to be closed by a SessionStart shell hook that injected the `rules`
  lane as runtime context. That mechanism shipped and was never installed on any
  agent, so it is removed (spec agent-registry FR-043…FR-048); the `rules` lane it was to
  deliver was itself deleted on 2026-09-11, once it was clear nothing read it.
  The gap is therefore **open again**: nothing pushes knowledge into a session,
  and an agent reaches the shared store only by calling `coffer__search` itself.
  The rest of this ADR stands; this bullet does not.
- **Import, never project.** _Withdrawn 2026-09-10._ Coffer could read an
  agent's own accumulated native memory and let the user adopt it inward, once.
  That too shipped unused and is removed (spec agent-registry FR-040/FR-041). The
  *direction* it established still holds — nothing flows back out into the
  agent's files — but there is no longer a path in either.

**The mechanism this ADR originally chose was different, and was removed.** It
projected the canonical store *outward* into each agent's native location — an
`AgentMemoryAdapter` per agent with a `projection_mode` of
`SYMLINK | RENDER | NONE`, symlinking the canonical directory into Claude
Code's auto-memory path, rendering a marker-fenced managed block into Codex
config files, and **disabling each agent's own native memory** so the canonical
store stayed the only writer.
[Memory via MCP](memory-via-mcp-not-native-projection.md) withdrew all of it
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

- **Retrieval is deliberate, not automatic.** An agent sees a fact only when it
  calls `coffer__search`. Since the session-start injection was removed
  (2026-09-10) *nothing* is ambient. This is the full cost of not writing the
  agent's files, and it is accepted knowingly: the ambient path had never
  actually run.
- **Facts in an agent's own native store stay there.** They do not migrate on
  their own, and since the import was removed there is no longer a way to bring
  them across.
- **Coffer's tools are the only write path.** An agent that cannot speak MCP
  cannot contribute to the shared store.
- **What an agent wrote may later be rewritten.** The periodic tidy
  (2026-09-11) merges duplicate notes and rewrites them into topic documents,
  unattended and on a timer. One shared store makes that worth doing — the
  duplicates it heals are the same fact written by several agents — but a note
  an agent wrote is not a fixed artefact. `.history/` keeps the prior
  revision and is the whole safety net; there is no review step before a pass
  lands.

## Alternatives Considered

**A silo per agent, as in the original mem0-based memory design.** Rejected: it is the drift this ADR
exists to remove.

**Native projection per agent (the original mechanism here).** Symlink where
the format already matches, a managed block where it does not, and disable the
agent's own native memory so copies cannot diverge. Superseded by Memory via MCP:
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
(see [Files as Truth](files-as-truth-sqlite-retrieval.md)'s revision history).
The substrate was shared from the start; only the facade was two, and it made
callers guess which face a fact belonged to. Rejected in retrospect: sharing a
store across agents is the point, and a second face over the same store is a
second thing to keep in sync for no gain.

## Revision history

- **2026-06-09** — Initial decision: one canonical per-fact-markdown memory
  store, shared across agents by a hybrid of MCP read/write plus per-agent
  native projection (`SYMLINK | RENDER | NONE`), with each projected agent's own
  native memory disabled. Scope was two-layer: global + per-project.
- **2026-06-18** — [Memory via MCP](memory-via-mcp-not-native-projection.md)
  removed the projection half: Coffer never writes or disables an agent's native
  memory files. The shared-store half was unaffected.
- **2026-09-10** — Re-expressed for the knowledge-layer merge. The store this
  ADR shares across agents is now the single `knowledge` kind (`memory` and
  `knowledge_base` merged); store names became the three scopes; the twelve
  `coffer__*` memory/KB tools became eight. The decision — one shared store, not
  one per agent — is unchanged; only the vocabulary it is written in has moved.
- **2026-09-11** — **Two lanes, six tools.** The store shared across agents keeps
  exactly two lanes: `notes/`, everything an agent or the user wrote, with
  `coffer__write` landing directly in it, and `docs/`, uploaded documents
  normalized to markdown — plus the hidden `.history/` and `.raw/`. The
  `knowledge/inbox/` gradient, `rules/`, `handoff/` and `superseded/` are
  deleted, destructively and without a holding pen. The tool surface drops from
  eight to six: `coffer__set_handoff` and `coffer__resume` retire with the
  handoff lane, so continuity across sessions and agents is now carried by
  ordinary notes rather than a lane of its own. The `rules` lane goes outright —
  its delivery channel was already removed on 2026-09-10 and nothing read it —
  which closes the last thread of the withdrawn ambient-delivery bullet above.
  `notes/` is instead kept readable by a periodic tidy that merges duplicates
  and rewrites notes into topic documents, keeping the prior revision in
  `.history/` (see [Files as Truth](files-as-truth-sqlite-retrieval.md)'s
  revision history). The AI-assisted merge of duplicate per-project scopes is
  deleted with it: worktree-aware `git_root` removed the cause, and the residue
  is healed at every daemon start, so a manual second path over the same problem
  is not worth its abstraction. The decision itself — one shared store, reached
  over MCP, never written into an agent's own memory files — is untouched.


- **2026-09-12 — the shape below is history; the decision is not.** The layer
  became a directory of markdown files an agent greps
  ([Knowledge Is Plain Files](knowledge-is-plain-files.md)): one lane instead of
  two, collections instead of three kinds of scope, five tools instead of six,
  and no index at all. Everything this ADR says about `notes/` ÷ `docs/`,
  `project-<ULID>` scopes, `coffer__search` and the SQLite substrate describes a
  layout that no longer exists. What it decided — **one store, shared by every
  agent, reached over MCP, never written into an agent's own memory files** — is
  exactly what that redesign preserved, which is why this ADR is not retired.
