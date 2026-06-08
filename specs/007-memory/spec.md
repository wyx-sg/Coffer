# Feature Specification: Memory (Shared Agent Memory)

> 中文版: [spec.zh.md](./spec.zh.md)

**Feature Branch**: `feature/kb-memory-redesign`
**Created**: 2026-05-22
**Status**: Draft (redesign)
**Input**: Redesign of Coffer's memory feature — the **memory face** of one unified substrate shared with the knowledge base (spec 006). Memory is no longer a mem0 vector store with an LLM at write time; it becomes a **single shared source of truth across agents** (no divergent per-agent copies), agent-native where the format matches. Canonical storage is per-fact markdown files plus a `MEMORY.md` index — Claude Code's auto-memory format — under `~/.coffer/memory/`, with a two-layer scope (global + per-project). Agents read/write through Coffer's MCP gateway; canonical files are also **projected** into each agent's native location (Claude Code via a directory symlink, Codex via a marker-fenced managed block in `AGENTS.md`). The user does full CRUD in the Coffer UI. Retrieval uses the same engine as the knowledge base (grep / keyword FTS5+BM25 / vector sqlite-vec). See [`docs/superpowers/specs/2026-06-09-kb-memory-redesign-design.md`](../../docs/superpowers/specs/2026-06-09-kb-memory-redesign-design.md).

## User Scenarios & Testing

### User Story 1 — One memory, every agent (Priority: P1)

The developer works on a project with Claude Code in the morning and Codex in the afternoon. While using Claude Code the agent learns "this repo deploys via `make release`, never `git push --tags` directly" and records it through Coffer's `coffer__remember` tool. In the afternoon, Codex — a different agent — recalls the same fact because both agents read and write **one shared store**, and the fact is also projected into each agent's native memory location. No copy diverges.

**Why this priority**: This is the core of the redesign. A per-agent silo that drifts across agents is the problem being solved; without a single shared source of truth there is no feature.

**Independent Test**: From a fresh install, run an MCP client in a git project, call `coffer__remember` with a project fact, then from a second MCP client (different agent identity) in the same project call `coffer__recall` and observe the fact returned. Confirm the same fact appears in the project's canonical `MEMORY.md`.

**Covering scenarios**:

- agent remembers a project fact
- agent recalls a project fact
- recall spans project and global scope
- agent updates a fact
- agent forgets a fact

---

### User Story 2 — Global and per-project memory (Priority: P1)

Some facts are about the developer everywhere ("prefers tabs over spaces"); others are about one repo ("this service's API base path is `/api/v2`"). The developer wants global facts available in every project and project facts confined to their project, with `recall` returning both by default.

**Why this priority**: Mixing personal preferences with project-specific facts pollutes recall and leaks repo details across projects. Two-layer scope is what makes the shared store trustworthy.

**Independent Test**: Remember one fact with `scope=global` and one with `scope=project`. From a different project, recall returns only the global fact; from the original project, recall returns both.

**Covering scenarios**:

- remember at global scope
- remember at project scope
- project scope resolves from the agent's working directory
- recall spans project and global scope

---

### User Story 3 — Native projection into each agent (Priority: P1)

The developer keeps Claude Code's auto-memory on. Coffer makes the project's canonical memory directory **be** Claude's project memory (a directory symlink), so Claude's own edits are canonical and instantly visible to every other agent. For Codex, Coffer renders the same facts into a marker-fenced managed block in `AGENTS.md` and disables Codex's native `memories` so no second copy accumulates.

**Why this priority**: Projection is what makes memory agent-native rather than "yet another MCP store the agent must be told to use." Without it the shared store is not actually shared into the agents' own surfaces.

**Independent Test**: Bind a project to Claude Code; confirm `~/.claude/projects/<slug>/memory/` is a symlink to the canonical dir and editing a fact through the symlink is returned by `coffer__recall`. Bind to Codex; confirm `AGENTS.md` gains a `<!-- coffer:memory:start -->…<!-- coffer:memory:end -->` block containing the facts and that Codex `memories` is disabled.

**Covering scenarios**:

- project memory projects into Claude as a symlink
- global memory renders a managed block into Codex AGENTS.md
- edits through the Claude symlink are visible on recall
- re-rendering a managed block is idempotent
- existing native memory files are merged, never overwritten

---

### User Story 4 — User curates memory in Coffer (Priority: P2)

The developer wants to see and correct what agents remember: browse facts per scope, fix one that drifted, add a fact by hand, delete a wrong one — all from the Coffer UI or CLI.

**Why this priority**: Memory without human curation is uncomfortable; agents sometimes record wrong things. Curation makes the feature safe to leave on.

**Independent Test**: After agents have written facts, open the memory view, edit one fact's text, save, and observe the next `recall` returns the edited version. Add a fact (actor=user), then delete a different one and observe it gone from disk and recall.

**Covering scenarios**:

- user adds a fact
- user edits a fact
- user deletes a fact
- writing a fact regenerates MEMORY.md

---

### User Story 5 — Inspect and reset memory (Priority: P3)

The developer wants to know how much memory has accumulated per scope and to clear a scope without deleting the store.

**Why this priority**: Hygiene; not blocking the core flow.

**Independent Test**: View per-store metrics (fact count, disk bytes). Clear the project scope; confirm every fact is gone but the store remains, ready for new facts, and projections re-render empty.

**Covering scenarios**:

- per-store metrics
- clear a memory scope

---

### Edge Cases

- **Vector requested but embedding unconfigured**: `recall` with `mode=vector` falls back to keyword and flags the fallback in the response; it never blocks. Default retrieval is keyword+grep (zero config, offline).
- **Claude's memory dir already has real files**: on first projection Coffer merges those files into the canonical store, then replaces the dir with a symlink — it never silently overwrites.
- **Claude rewrites `MEMORY.md`**: harmless — Coffer regenerates `MEMORY.md` from fact frontmatter idempotently on the next write or recall.
- **Direct disk edit of a fact file**: the next `recall` lazily scans the small fact dir for deltas and reindexes, so out-of-band edits are picked up with no watcher.
- **Empty fact text**: rejected at the API boundary; nothing written.
- **Fact text too long**: bounded at the API boundary (`max_fact_chars`, default 8192); rejected before any write.
- **Project scope unresolved**: if the agent's working directory is not inside a git project, `scope=project` is rejected with a clear error; `scope=global` still works.
- **Agent with no projection (`projection_mode = NONE`)**: memory still works fully over MCP; only native projection is skipped.

## Acceptance Scenarios

Every scenario maps to at least one test marked `@pytest.mark.acceptance(spec="007-memory", scenario="…")`.

### Scenario: agent remembers a project fact

- **Given** an MCP client running inside a git project,
- **When** it calls `coffer__remember` with a fact and `scope=project`,
- **Then** a per-fact markdown file (YAML frontmatter `name`/`description`/`metadata.type`/`origin_session_id` + body) is written under the project memory dir, `MEMORY.md` is regenerated, the file is indexed into `documents`, and an audit entry is recorded.

### Scenario: agent recalls a project fact

- **Given** a project memory store with facts,
- **When** an MCP client calls `coffer__recall` with a query,
- **Then** ranked facts are returned with id, text, score, source, and time, after a lazy reindex scan of the fact dir picks up any out-of-band deltas.

### Scenario: recall spans project and global scope

- **Given** facts exist at both global and project scope,
- **When** an MCP client calls `coffer__recall` without a scope,
- **Then** results are drawn from both the project store and the global (sentinel) store.

### Scenario: remember at global scope

- **Given** an MCP client,
- **When** it calls `coffer__remember` with `scope=global`,
- **Then** the fact is written to the global store keyed by `project_id = WORKSPACE_GLOBAL_PROJECT_ID` and recall from any project returns it.

### Scenario: project scope resolves from the agent's working directory

- **Given** the coffer-mcp-shim reports its launch cwd at session handshake,
- **When** the daemon resolves the project memory store,
- **Then** it computes the git-root of that cwd and resolves (lazily provisioning if absent) the per-project store keyed by that project's ULID.

### Scenario: agent updates a fact

- **Given** a fact exists,
- **When** an MCP client calls `coffer__update_memory` with the fact id and new text,
- **Then** the canonical markdown is rewritten, the document is reindexed, `MEMORY.md` is regenerated, and recall reflects the new text.

### Scenario: agent forgets a fact

- **Given** a fact exists,
- **When** an MCP client calls `coffer__forget` with the fact id,
- **Then** the markdown file is deleted, its index rows are removed, `MEMORY.md` is regenerated, projections re-render, and recall no longer returns it.

### Scenario: project memory projects into Claude as a symlink

- **Given** a project bound to a Claude Code agent,
- **When** projection is established,
- **Then** `~/.claude/projects/<slug>/memory/` is a directory symlink to the canonical project memory dir and Claude auto-memory stays on.

### Scenario: edits through the Claude symlink are visible on recall

- **Given** a project memory store symlinked into Claude,
- **When** a fact file is edited through the symlink path,
- **Then** the next `coffer__recall` returns the edited content (lazy reindex-on-read), with no filesystem watcher running.

### Scenario: global memory renders a managed block into Codex AGENTS.md

- **Given** a Codex agent at the global layer,
- **When** projection runs,
- **Then** `~/.codex/AGENTS.md` contains a `<!-- coffer:memory:start (managed, do not edit) -->…<!-- coffer:memory:end -->` block holding the rendered facts, content outside the markers is untouched, and Codex native `memories` is disabled.

### Scenario: re-rendering a managed block is idempotent

- **Given** an `AGENTS.md` already carrying a managed block,
- **When** the facts are unchanged and projection runs again,
- **Then** the file content is byte-identical (idempotent render).

### Scenario: existing native memory files are merged, never overwritten

- **Given** Claude's project memory dir already holds real fact files before binding,
- **When** Coffer establishes projection,
- **Then** those files are merged into the canonical store first, then the dir is replaced by a symlink — no file is silently overwritten.

### Scenario: user adds a fact

- **Given** a memory store,
- **When** the user adds a fact via the Coffer UI or CLI,
- **Then** the canonical markdown is written with `metadata.actor = "user"`, `MEMORY.md` is regenerated, the document is indexed, and an audit entry is recorded.

### Scenario: user edits a fact

- **Given** a fact exists,
- **When** the user edits its text and saves,
- **Then** the canonical markdown is rewritten, the document is reindexed, and recall reflects the new text.

### Scenario: user deletes a fact

- **Given** a fact exists,
- **When** the user deletes it,
- **Then** the markdown file and its index rows are removed, `MEMORY.md` is regenerated, and recall no longer returns it.

### Scenario: writing a fact regenerates MEMORY.md

- **Given** any writer (agent, Claude, or user) writes or removes a fact,
- **When** the write completes,
- **Then** `MEMORY.md` is regenerated from fact frontmatter as `- [name](file.md) — description`, overwriting any prior content idempotently.

### Scenario: clear a memory scope

- **Given** a memory store with facts,
- **When** the user clears that scope,
- **Then** every fact file and its index rows are removed, `MEMORY.md` becomes empty, projections re-render empty, but the store Resource is preserved.

### Scenario: built-in memory tools appear in client tool list

- **Given** an MCP client connects to coffer's gateway,
- **When** the client lists tools,
- **Then** `coffer__recall`, `coffer__remember`, `coffer__update_memory`, `coffer__forget`, and `coffer__list_memory` appear alongside other built-in and upstream tools.

### Scenario: vector recall falls back when embedding is unconfigured

- **Given** a memory store with no embedding provider configured,
- **When** `coffer__recall` is called with `mode=vector`,
- **Then** the call returns keyword results and flags the fallback in the response (never an error).

> **Deferred to future test work** (tests land with the e2e infrastructure; `make verify-acceptance` does not gate on them): desktop memory list view per scope, desktop edit-in-place, CLI `coffer memory …` end-to-end with a running daemon, per-store metrics (HTTP route).

## Requirements

### Functional Requirements

**Storage & scope**

- **FR-001**: System MUST store every memory fact as a per-fact markdown file with YAML frontmatter (`name`, `description`, `metadata.type`, `metadata.actor`, `origin_session_id`) plus a markdown body, alongside a regenerated `MEMORY.md` index. The markdown files are the **sole source of truth**; SQLite is a rebuildable index.
- **FR-002**: System MUST support two memory scopes: **global** (one store keyed by `project_id = WORKSPACE_GLOBAL_PROJECT_ID`, the existing sentinel `00000000000000000000000000`) and **per-project** (one store per project, keyed by the project's ULID), stored under `~/.coffer/memory/global/` and `~/.coffer/memory/projects/<project-ulid>/` respectively.
- **FR-003**: System MUST regenerate `MEMORY.md` (`- [name](file.md) — description`, derived from fact frontmatter) on every write/update/delete, idempotently, overwriting any prior content.
- **FR-004**: System MUST resolve the per-project store from the agent's reported launch cwd at session handshake: the daemon computes the git-root and resolves — lazily provisioning if absent — the store for that project's ULID.

**Fact lifecycle**

- **FR-005**: Agents and users MUST be able to write a fact directly (no LLM at write time). Fact text MUST be at least 1 char and at most `max_fact_chars` (default 8192); empty or over-long text is rejected at the API boundary with nothing persisted.
- **FR-006**: Users and agents MUST be able to list facts (per scope), get a single fact by id, edit a fact's text, delete a single fact, and clear all facts in a scope. Clearing preserves the store Resource.
- **FR-007**: Every fact carries `metadata.actor` (`agent` | `user`) and an optional `metadata.type` (e.g. `project` / `feedback` / `reference` / `user`); the writer sets these.

**Retrieval**

- **FR-008**: Recall MUST use the unified retrieval engine shared with the knowledge base: `grep` (raw files), `keyword` (FTS5 BM25, the default), and `vector` (sqlite-vec with a configurable embedding provider). When `vector` is requested but no embedding provider is configured, recall MUST fall back to `keyword` and flag the fallback in the response — never block.
- **FR-009**: `coffer__recall` MUST default to spanning both the project and global stores; results carry id, text, score, source, and time. Default `top_k` is 5; callers MAY specify 1–20.
- **FR-010**: Memory MUST use **lazy reindex-on-read**: `recall` first scans the fact directory for deltas (added/changed/removed files by content hash) and reconciles the index before searching, so out-of-band edits (including Claude's symlink edits) are visible immediately with no filesystem watcher.

**Projection & binding**

- **FR-011**: An `AgentMemoryAdapter` (living with the agent driver, not the memory kind) MUST declare a `projection_mode` of `SYMLINK`, `RENDER`, or `NONE`, and the projection engine MUST dispatch on it. Adding a new agent MUST require only a new adapter — no change to the memory substrate.
- **FR-012**: For Claude Code, the project layer MUST project the canonical project memory directory as a **directory symlink** into `~/.claude/projects/<slug>/memory/` (bidirectional; auto-memory stays on). If a real memory directory already exists there, Coffer MUST merge its files into the canonical store first and only then replace it with a symlink — never silently overwrite.
- **FR-013**: For Codex, Coffer MUST render the facts into a marker-fenced managed block `<!-- coffer:memory:start (managed, do not edit) -->…<!-- coffer:memory:end -->` in `<project>/AGENTS.md` (project layer) and `~/.codex/AGENTS.md` (global layer), MUST leave all content outside the markers untouched, MUST re-render idempotently, and MUST disable Codex native `memories` so no second copy accumulates.
- **FR-014**: The adapter (agent layer) MUST perform all native-file mutations; the memory substrate MUST only provide canonical files plus rendered markdown, keeping memory agent-agnostic and the L1 config boundary clean.

**Agent integration via MCP**

- **FR-015**: Coffer's MCP gateway MUST expose built-in tools `coffer__recall(query, scope?, top_k?)`, `coffer__remember(text, scope?, type?)`, `coffer__update_memory(id, text)`, `coffer__forget(id)`, and `coffer__list_memory(scope?)`, namespaced under the reserved `coffer__` prefix. `remember` defaults to `scope=project`; `recall` defaults to both scopes.
- **FR-016**: Built-in memory tool invocations MUST share the existing invocation-logging surface (one `mcp_invocations` row: tool name + who/when/duration/outcome only — no arguments or returned content).

**Surfaces**

- **FR-017**: Users MUST be able to perform full memory CRUD through (a) a REST API under `/api/v1/memory_stores/`, (b) `coffer memory …` subcommands, and (c) a desktop UI. User writes set `metadata.actor = "user"`, write the canonical markdown, regenerate `MEMORY.md`, reindex, and audit.

**Substrate isolation**

- **FR-018**: The retrieval/index engine (FTS5, sqlite-vec, embedding providers, converters) MUST be confined to infrastructure. Domain and application layers MUST NOT import index/engine types directly; interaction is via the shared retrieval port. mem0, chroma, and LlamaIndex MUST NOT be imported anywhere.

**Migration**

- **FR-019**: This branch is unreleased; there is **no data migration**. A single migration MUST drop `memory_records`, delete any chroma/LlamaIndex directories, and create the fresh unified schema. Old mem0/chroma text is not migrated.

### Key Entities

- **Memory Store** (a resource of kind `memory`): one store per scope — the global store (sentinel ULID) or a per-project store (project ULID). Config holds enabled retrieval modes, embedding config, and `max_fact_chars`.
- **Memory Fact** (one markdown file = one `documents` row): `id`, `name`, `description`, body, `metadata` (`type`, `actor`, `origin_session_id`), `path`, `content_sha256`, `created_at`, `updated_at`. The markdown file is the source of truth.
- **Memory Hit** (recall result, not persisted): `id`, `text`/passage, `score`, `source`, `time`.
- **Projection** (per agent × scope): a `projection_mode` (`SYMLINK` | `RENDER` | `NONE`) plus the native target path the adapter owns.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A fact written by one agent via `coffer__remember` is recalled by a different agent via `coffer__recall` in the same project within one session, with no per-agent copy diverging.
- **SC-002**: A fact edited through Claude's project memory symlink is returned by `coffer__recall` on the next call, with no filesystem watcher running.
- **SC-003**: With 200 facts in a scope, recall latency for a typical keyword query is ≤ 300 ms wall-clock on a developer laptop.
- **SC-004**: Default retrieval works offline with zero configuration (keyword + grep); vector recall is opt-in and degrades to keyword (flagged) when unconfigured — it never errors.
- **SC-005**: Adding a new agent's projection requires only a new `AgentMemoryAdapter` and no change under the memory substrate (verified by the adapter dispatch test).
- **SC-006**: Every Acceptance Scenario is covered by at least one test marked `acceptance(spec="007-memory", scenario="…")`.
- **SC-007**: Substrate isolation is enforced by importlinter: no module under `coffer.application.*` or `coffer.domain.*` imports the index engine, and `mem0`/`chroma`/`llama_index` are imported nowhere.
- **SC-008**: `make verify` passes locally and in CI.

## Assumptions

- The user runs Coffer on their own machine; memory data stays local. Calling a configured cloud embedding provider for opt-in vector recall is allowed (local-first ≠ no remote API calls).
- The canonical format is Claude Code's auto-memory format, adopted so Claude projection is a native symlink.
- The coffer-mcp-shim propagates its launch cwd to the daemon at session handshake on the supported agents (to verify in implementation).
- The knowledge base (spec 006) and memory share one unified substrate (`documents` table discriminated by `kind` + JSON `metadata`); they are two faces, not duplicated code.
- Single-user concurrency is small.
