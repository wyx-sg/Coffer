# Feature Specification: Memory (Shared Agent Memory)

> 中文版: [spec.zh.md](./spec.zh.md)

**Feature Branch**: `feature/kb-memory-redesign`
**Created**: 2026-05-22
**Status**: Accepted (redesign — in development)
**Input**: Redesign of Coffer's memory feature — the **memory face** of one unified substrate shared with the knowledge base (spec 006). Memory is no longer a mem0 vector store with an LLM at write time; it becomes a **single shared source of truth across agents** (no divergent per-agent copies). Canonical storage is per-fact markdown files plus a `MEMORY.md` index under `~/.coffer/memory/`, with a two-layer scope (global + per-project). Agents read and write memory **only through Coffer's MCP gateway** (`coffer__recall`/`remember`/`update_memory`/`forget`/`list_memory`); Coffer keeps its own canonical format and does not touch agents' native memory files (native projection was removed — see ADR-026). The user does full CRUD in the Coffer UI. Retrieval uses the same engine as the knowledge base (grep / keyword FTS5+BM25 / vector sqlite-vec). See [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md) for the full design rationale.

## User Scenarios & Testing

### User Story 1 — One memory, every agent (Priority: P1)

The developer works on a project with Claude Code in the morning and Codex in the afternoon. While using Claude Code the agent learns "this repo deploys via `make release`, never `git push --tags` directly" and records it through Coffer's `coffer__remember` tool. In the afternoon, Codex — a different agent — recalls the same fact because both agents read and write **one shared store**. No copy diverges.

**Why this priority**: This is the core of the redesign. A per-agent silo that drifts across agents is the problem being solved; without a single shared source of truth there is no feature.

**Independent Test**: From a fresh install, run an MCP client in a git project, call `coffer__remember` with a project fact, then from a second MCP client (different agent identity) in the same project call `coffer__recall` and observe the fact returned. Confirm the same fact appears in the project's canonical `MEMORY.md`.

**Covering scenarios**:

- agent remembers a project fact
- agent recalls a project fact
- recall spans project and global scope
- agent updates a fact
- agent forgets a fact
- built-in memory tools appear in client tool list
- vector recall falls back when embedding is unconfigured

---

### User Story 2 — Global and per-project memory (Priority: P1)

Some facts are about the developer everywhere ("prefers tabs over spaces"); others are about one repo ("this service's API base path is `/api/v2`"). The developer wants global facts available in every project and project facts confined to their project, with `recall` returning both by default.

**Why this priority**: Mixing personal preferences with project-specific facts pollutes recall and leaks repo details across projects. Two-layer scope is what makes the shared store trustworthy.

**Independent Test**: Remember one fact with `scope=global` and one with `scope=project`. From a different project, recall returns only the global fact; from the original project, recall returns both.

**Covering scenarios**:

- remember at global scope
- agent remembers a project fact
- project scope resolves from the agent's working directory
- recall spans project and global scope

---

### User Story 4 — User curates memory in Coffer (Priority: P2)

The developer wants to see and correct what agents remember: browse facts per scope in a **read-only** viewer, then fix one that drifted **in their own external editor** (or via the API/CLI), add a fact by hand, delete a wrong one. The Coffer UI never edits fact content in-app; instead each fact and its containing folder offer "open in external editor", "reveal in file manager", and (web fallback) "copy absolute path", and any out-of-band correction is picked up by the existing lazy reindex-on-read (FR-010).

**Why this priority**: Memory without human curation is uncomfortable; agents sometimes record wrong things. Curation makes the feature safe to leave on — and routing edits through the user's own editor keeps the markdown files the sole source of truth without a second editing surface to keep in sync.

**Independent Test**: After agents have written facts, open the memory view (read-only) and confirm fact content renders but is not editable in-app. Open one fact in an external editor (or `coffer memory edit`/PATCH), correct its text outside Coffer, and observe the next `recall` returns the corrected version (lazy reindex-on-read). Add a fact (actor=user) via the CLI/API, then delete a different one and observe it gone from disk and recall.

**Covering scenarios**:

- user adds a fact
- user corrects a fact out-of-band
- user deletes a fact
- writing a fact regenerates MEMORY.md
- read-only viewer offers open/reveal/copy-path affordances

---

### User Story 6 — Distil insights from an agent's past conversations into shared memory (Priority: P2)

The developer has been working on a project with Claude Code for weeks. Many
engineering decisions, failed approaches, and project conventions were
discussed and settled in those sessions, but never explicitly recorded as
memory facts. The developer runs `coffer transcript distill claude_code
--project /repo` (or clicks "Distil to memory" in the Coffer UI). Coffer
reads the local `.jsonl` transcript files, scrubs tool payloads and secrets,
asks an LLM to extract durable insights, and writes them as project-scoped
memory facts. From that point on, any agent — including Codex on a second
machine — can recall those facts through `coffer__recall`, because memory is
shared (Spec 007) and synced (Spec 010). No raw transcript content is ever
stored or transmitted. When the transcript's working directory resolves to a
git project, the extracted facts are written project-scoped to that project's
memory store; when the path is not inside a git work-tree, facts fall back to
the global memory store.

**Why this priority**: Agents accumulate institutional knowledge in local
transcripts that is otherwise siloed per-session and inaccessible to other
agents. Distillation is the least-invasive mechanism to surface that
knowledge: it produces standard memory facts, inheriting cross-agent sharing
and multi-machine sync for free. It is P2 (not P1) because the core shared
memory flow (Stories 1–2) must work first — distillation is additive on top
of it. See [ADR-020](../../docs/decisions/ADR-020-transcript-distillation.md)
for the full decision rationale and rejected alternatives.

**Supported transcript readers**: distillation reads each agent's native local
store through a versioned, defensive per-agent reader. **Claude Code** and
**Codex** read one `.jsonl` file per session under the agent's config dir;
**OpenCode** reads its multi-file JSON storage tree under the XDG data dir
(`~/.local/share/opencode/storage/{project,session,message,part}`), joining the
records into sessions with the project working directory taken from the project
record. Readers for **Cursor**, **OpenClaw**, and **Hermes** are deferred: their
formats can't be read reliably for project-scoped distillation today — Cursor's
`agent-transcripts/*.jsonl` are ephemeral (emptied on restart) with the durable
state in an internal `vscdb` SQLite; OpenClaw's session format is undocumented;
and Hermes sessions are cross-platform chat sessions that record no working
directory, so they can't be scoped to a project. Distillation for those agents
returns an explicit "unsupported agent" error rather than guessing.

**Independent Test**: From a project with at least one Claude Code, Codex, or
OpenCode transcript in the agent's native store, run
`coffer transcript distill <agent> --project <path> --dry-run` and observe
at least one insight printed without any fact being written to disk. Then run
without `--dry-run` and confirm via `coffer memory recall <store> "<topic>"`
that at least one distilled fact is now retrievable, carries
`actor="agent"` and a non-empty `origin_session_id`, and contains no tool
payloads, file contents, or secret-like strings.

**Covering scenarios**:

- distill transcript to memory

---

### User Story 5 — Inspect, name, and reset memory (Priority: P3)

The developer wants to know how much memory has accumulated per scope, to give a store a readable name when its originating folder is unknown, and to clear a scope without deleting the store.

**Why this priority**: Hygiene; not blocking the core flow.

**Independent Test**: View per-store metrics (fact count, disk bytes). Rename a store whose folder is unknown and confirm the chosen name shows in the list and survives a reload. Clear the project scope; confirm every fact is gone but the store remains, ready for new facts.

**Covering scenarios**:

- clear a memory scope
- user renames a memory store

(The per-store metrics HTTP route is exercised by the independent test but its dedicated acceptance test is deferred — see the note after the scenarios.)

---

### User Story 7 — Continue the same work across agents and machines (Priority: P2)

The developer pauses mid-task with Claude Code — at a known step, with specific
next steps and files in flight — and later resumes from a different agent (Codex)
or a second machine. Before pausing the agent calls `coffer__set_handoff` with
the current working state ("现场"): what it was doing, what's next, which files
are open, and any unresolved questions. Coffer keys that scene by **(project ×
git branch)** and writes it as a file under the project's memory store, so it
rides the existing git sync mirror. When work resumes, the agent calls
`coffer__resume`, which returns the saved scene for the current branch (annotated
with how stale it may be) — or reports that none exists for a fresh branch.

**Why this priority**: Continuity is the redesign's north star, but it builds on
the shared-memory core (Stories 1–2): a handoff is an additive working-memory
lane, not a prerequisite for recall. Branch-keying means parallel branches /
worktrees keep independent scenes and never clobber each other; there is no
global handoff (a global "current task" is meaningless), so a cwd outside any
git project has nothing to resume.

**Independent Test**: From an MCP client inside a git project on branch `work`,
call `coffer__set_handoff` with a body, then from a second client (different
agent identity) in the same project + branch call `coffer__resume` and observe
the same body returned with the branch and a freshness annotation. On a fresh
branch with no prior handoff, `coffer__resume` reports `found=false`.

**Covering scenarios**:

- agent saves and resumes a working-state handoff
- resume reports no handoff for a fresh branch

---

### Edge Cases

- **Vector requested but embedding unconfigured**: `recall` with `mode=vector` falls back to keyword and flags the fallback in the response; it never blocks. Default retrieval is keyword+grep (zero config, offline).
- **Resume on a fresh branch**: when no handoff has been saved for the current (project × branch), `coffer__resume` returns `found=false` rather than erroring; nothing is fabricated.
- **Handoff outside a git project**: a cwd not inside a git project has no project scope and no branch, so `coffer__resume` returns `found=false` and `coffer__set_handoff` is rejected (there is no global handoff).
- **Direct disk edit of a fact file**: the next `recall` lazily scans the small fact dir for deltas and reindexes, so out-of-band edits are picked up with no watcher.
- **Empty fact text**: rejected at the API boundary; nothing written.
- **Fact text too long**: bounded at the API boundary (`max_fact_chars`, default 8192); rejected before any write.
- **Project scope unresolved**: if the agent's working directory is not inside a git project, `scope=project` is rejected with a clear error; `scope=global` still works.

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
- **Then** the markdown file is deleted, its index rows are removed, `MEMORY.md` is regenerated, and recall no longer returns it.

### Scenario: out-of-band fact-file edits are visible on recall

- **Given** a project memory store with facts,
- **When** a fact file is edited out-of-band directly on disk (frontmatter preserved),
- **Then** the next `coffer__recall` returns the edited content (lazy reindex-on-read), with no filesystem watcher running.

### Scenario: user adds a fact

- **Given** a memory store,
- **When** the user adds a fact via the Coffer UI or CLI,
- **Then** the canonical markdown is written with `metadata.actor = "user"`, `MEMORY.md` is regenerated, the document is indexed, and an audit entry is recorded.

### Scenario: user corrects a fact out-of-band

- **Given** a fact exists,
- **When** the user corrects its text outside the in-app viewer — via the REST/CLI write surface (`PATCH …/facts/{id}` / `coffer memory edit`) or by editing the canonical markdown directly in an external editor,
- **Then** the canonical markdown is rewritten, the document is reindexed (immediately for the REST/CLI path; on the next `recall` via lazy reindex-on-read for a direct file edit), and recall reflects the new text.

### Scenario: user deletes a fact

- **Given** a fact exists,
- **When** the user deletes it,
- **Then** the markdown file and its index rows are removed, `MEMORY.md` is regenerated, and recall no longer returns it.

### Scenario: read-only viewer offers open/reveal/copy-path affordances

- **Given** a fact viewed in the Coffer UI,
- **When** the user inspects the fact (and its containing folder),
- **Then** the content renders read-only (no in-app content editing), the read responses surface the fact's absolute on-disk `.md` path and its containing folder's absolute path, and the UI offers "open in external editor" + "reveal in file manager" for both the file and the folder on desktop (Tauri) and a "copy absolute path" fallback on web; which editor opens is decided by the global preferred-editor preference (see 002-ui-shell).

### Scenario: writing a fact regenerates MEMORY.md

- **Given** any writer (agent, Claude, or user) writes or removes a fact,
- **When** the write completes,
- **Then** `MEMORY.md` is regenerated from fact frontmatter as `- [name](file.md) — description`, overwriting any prior content idempotently.

### Scenario: clear a memory scope

- **Given** a memory store with facts,
- **When** the user clears that scope,
- **Then** every fact file and its index rows are removed, `MEMORY.md` becomes empty, but the store Resource is preserved.

### Scenario: user renames a memory store

- **Given** a memory store (e.g. one whose originating folder was never recorded, so it would otherwise show as `project-<ULID>`),
- **When** the user sets a display label via `PATCH /memory_stores/{name}/label`,
- **Then** the label is trimmed, echoed back, surfaced on the store read + list as the readable name, and an empty / whitespace label clears it (reverting to the FR-017a derivation); renaming an unknown store is a 404, not an autocreate.

### Scenario: built-in memory tools appear in client tool list

- **Given** an MCP client connects to coffer's gateway,
- **When** the client lists tools,
- **Then** `coffer__recall`, `coffer__remember`, `coffer__update_memory`, `coffer__forget`, `coffer__list_memory`, `coffer__set_handoff`, and `coffer__resume` appear alongside other built-in and upstream tools.

### Scenario: vector recall falls back when embedding is unconfigured

- **Given** a memory store with no embedding provider configured,
- **When** `coffer__recall` is called with `mode=vector`,
- **Then** the call returns keyword results and flags the fallback in the response (never an error).

### Scenario: agent saves and resumes a working-state handoff

- **Given** an MCP client running inside a git project on a branch,
- **When** it calls `coffer__set_handoff` with a body and later (possibly as a different agent) calls `coffer__resume`,
- **Then** `set_handoff` writes a per-`(project × branch)` markdown file (frontmatter `branch`/`updated_at` + freeform body) under the project store's `handoff/` subdir — overwriting any prior scene for that branch and recording a `handoff_set` audit entry — and `resume` returns `found=true` with the saved branch, body, `updated_at`, and a freshness `note`; the handoff is never returned by `coffer__recall`.

### Scenario: resume reports no handoff for a fresh branch

- **Given** an MCP client in a git project on a branch with no saved handoff (or a cwd outside any git project),
- **When** it calls `coffer__resume`,
- **Then** the call returns `found=false` (never an error and nothing fabricated).

### Scenario: distill-transcript-to-memory

- **Given** a registered agent (Claude Code, Codex, or OpenCode) with at least
  one local transcript in its native store containing natural-language turns,
- **When** `POST /api/v1/agents/{name}/transcripts/distill` is called (or
  `coffer transcript distill <agent>` in the CLI) with `dry_run=false`,
- **Then** the transcript is read, tool payloads and secrets are scrubbed before
  the LLM call, the LLM returns structured insights, and each insight is written
  as a project-scoped memory fact with `actor="agent"`,
  `origin_session_id=<transcript session id>`, and `type` ∈
  `{decision, gotcha, convention, todo}`; no raw transcript content appears in
  any persisted fact; `coffer__recall` subsequently returns the new facts; and
  when `dry_run=true`, insights are returned but nothing is written to disk.

> **Deferred to future test work** (tests land with the e2e infrastructure; `make verify-acceptance` does not gate on them): desktop memory list view per scope, the desktop read-only fact viewer's open-in-editor / reveal / copy-path affordances, CLI `coffer memory …` end-to-end with a running daemon, per-store metrics (HTTP route).

## Requirements

### Functional Requirements

**Storage & scope**

- **FR-001**: System MUST store every memory fact as a per-fact markdown file with YAML frontmatter (`name`, `description`, `metadata.type`, `metadata.actor`, `origin_session_id`) plus a markdown body, alongside a regenerated `MEMORY.md` index. The markdown files are the **sole source of truth**; SQLite is a rebuildable index.
- **FR-002**: System MUST support two memory scopes: **global** (one store keyed by `project_id = WORKSPACE_GLOBAL_PROJECT_ID`, the existing sentinel `00000000000000000000000000`) and **per-project** (one store per project, keyed by the project's ULID), stored under `~/.coffer/memory/global/` and `~/.coffer/memory/projects/<project-ulid>/` respectively.
- **FR-003**: System MUST regenerate `MEMORY.md` (`- [name](file.md) — description`, derived from fact frontmatter) on every write/update/delete, idempotently, overwriting any prior content.
- **FR-004**: System MUST resolve the per-project store from the agent's reported launch cwd at session handshake: the daemon computes the git-root and resolves — lazily provisioning if absent — the store for that project's ULID.

**Fact lifecycle**

- **FR-005**: Agents and users MUST be able to write a fact directly (no LLM at write time). Fact text MUST be at least 1 char and at most `max_fact_chars` (default 8192); empty or over-long text is rejected at the API boundary with nothing persisted.
- **FR-006**: Users and agents MUST be able to list facts (per scope), get a single fact by id, edit a fact's text (via the REST/CLI write surface or by editing the canonical markdown directly — the Coffer UI renders fact content read-only and does not edit it in-app), delete a single fact, and clear all facts in a scope. Clearing preserves the store Resource.
- **FR-007**: Every fact carries `metadata.actor` (`agent` | `user`) and an optional `metadata.type` (e.g. `project` / `feedback` / `reference` / `user`); the writer sets these.

**Retrieval**

- **FR-008**: Recall MUST use the unified retrieval engine shared with the knowledge base: `grep` (served for real — ripgrep over the store's fact files; essential for content FTS5 cannot tokenize, e.g. CJK), `keyword` (FTS5 BM25, the default), and `vector` (sqlite-vec with a configurable embedding provider). When `vector` is requested but no embedding provider is configured, recall MUST fall back to `keyword` and flag the fallback as a boolean in the response — never block. The MCP `coffer__recall` response includes that `fallback` boolean.
- **FR-009**: `coffer__recall` MUST default to spanning both the project and global stores (an explicit `scope` narrows recall to one store: `project` = the project store only, `global` = the global store only); cross-store results are merged by reciprocal rank fusion (per-store scores are not comparable across modes/stores; each hit keeps its per-store score, only the merged order comes from the fusion). Results carry id, text, score, source, and time — `time` is the fact's `updated_at` and `source` is `<scope>:<fact file path>`. Default `top_k` is 5; callers MAY specify 1–20.
- **FR-010**: Memory MUST use **lazy reindex-on-read**: `recall` first scans the fact directory for deltas (added/changed/removed files by content hash) and reconciles the index before searching, so out-of-band edits — a human's corrections made in their own external editor, or any direct on-disk edit — are visible immediately with no filesystem watcher. This is the mechanism that makes external corrections appear, so the UI can stay a read-only viewer (FR-017) while curation happens in the user's editor.

**Agent integration via MCP**

- **FR-015**: Coffer's MCP gateway MUST expose built-in tools `coffer__recall(query, scope?, mode?, top_k?)` (`mode` ∈ `grep` | `keyword` | `vector`), `coffer__remember(text, scope?, type?)`, `coffer__update_memory(id, text)`, `coffer__forget(id)`, `coffer__list_memory(scope?)`, `coffer__set_handoff(body)`, and `coffer__resume()`, namespaced under the reserved `coffer__` prefix. `remember` defaults to `scope=project`; `recall` defaults to both scopes.
- **FR-016**: Built-in memory tool invocations MUST share the existing invocation-logging surface (one `mcp_invocations` row: tool name + who/when/duration/outcome only — no arguments or returned content).

**Working-state handoff (continuity)**

- **FR-023**: The system MUST provide a **working-state handoff** lane keyed by **(project store × git branch)**: one file per branch under `~/.coffer/memory/projects/<project-ulid>/handoff/<branch-slug>.md`, with YAML frontmatter (`branch`, `updated_at`) plus a freeform markdown body. The branch is resolved from the agent's reported cwd (its repo's current branch). Handoff is **per-project only** — there is no global handoff.
- **FR-024**: `coffer__set_handoff(body)` MUST **overwrite** the current branch's handoff file (no accumulation; one scene per branch), set `updated_at`, and record a `handoff_set` audit entry. The handoff body is files-as-truth on disk (it rides the git sync mirror like other memory files) and MUST NOT be returned by `coffer__recall` (it lives in the `handoff/` subdir, outside the recall glob).
- **FR-025**: `coffer__resume()` MUST return the current branch's saved handoff — `found=true` with `branch`, `body`, `updated_at`, and a freshness `note` annotating that the scene may be stale — or `found=false` when no handoff exists for the branch (a fresh branch) or the cwd is not inside a git project. It MUST never error on a missing handoff and MUST NOT fabricate content.
- **FR-026**: When the agent's cwd does not resolve to a git project (no project scope, no branch), `coffer__set_handoff` MUST be rejected (there is no store to write to and no global handoff) and `coffer__resume` MUST return `found=false`.

**Surfaces**

- **FR-017**: Users MUST be able to perform full memory CRUD through the programmatic write surfaces — (a) a REST API under `/api/v1/memory_stores/` and (b) `coffer memory …` subcommands. (The REST write endpoints are also what agents author facts through via the MCP gateway.) User writes set `metadata.actor = "user"`, write the canonical markdown, regenerate `MEMORY.md`, reindex, and audit. The desktop/web UI surfaces facts **read-only** (it does not edit fact content in-app); humans curate by editing the canonical markdown in their own external editor (picked up by lazy reindex-on-read, FR-010) or via the REST/CLI write surface. Store names on these surfaces are validated: only `global` or `project-<26-char ULID>` are legal — a well-formed name lazily provisions its store; anything else returns 404 (`MEMORY_STORE_NOT_FOUND`).
- **FR-017a**: Surfaces MUST present a per-project store by a **human-readable identity derived from its `project_root`** — the root directory's basename as the primary label and the absolute root path as a secondary detail — never only the opaque `project-<ULID>` store name (the project ULID is a one-way digest of the root and is not human-recognisable). When the root is unknown (a store provisioned before the root was tracked) the surface falls back to the store name; the global store needs no derivation (its name `global` is already readable). The underlying store name stays `project-<ULID>` (FR-017) — this is a **display** concern. Verified by frontend tests; desktop acceptance is deferred to e2e like the other desktop-view items.
- **FR-017c**: A user MUST be able to set a **display label** for any memory store — a chosen name that takes precedence over the FR-017a `project_root` derivation in every surface. This gives a readable identity to a store whose originating folder was never recorded (where FR-017a would otherwise fall back to the opaque `project-<ULID>` name). Setting an empty / whitespace label clears it, reverting to the FR-017a derivation or fallback. The label is **display metadata**: it does not change the store name (FR-017) or `project_id`, and is set via `PATCH /memory_stores/{name}/label`. Verified by an HTTP acceptance test; the desktop rename view is deferred to e2e like the other desktop-view items.
- **FR-021**: The read-only fact viewer MUST offer, for both a fact file and its containing folder, affordances to (a) **open in external editor**, (b) **reveal in file manager / Finder**, and (c) **copy the absolute path** (the web fallback). On the desktop (Tauri) build (a) and (b) perform a real open/reveal; on the web build the UI falls back to copy-path. Which editor opens is decided by the global preferred-editor preference (specced in 002-ui-shell; not re-specified here). The read responses MUST surface the absolute paths these affordances act on (see FR-022).
- **FR-022**: Read responses MUST surface the on-disk truth: the fact read endpoints (`GET …/facts`, `GET …/facts/{id}`) MUST include each fact file's absolute `.md` path and its containing folder's absolute path, and the store read endpoint (`GET …/{name}`) MUST include the store's absolute on-disk directory. These power the FR-021 open/reveal/copy-path affordances and let a human locate the canonical file to correct out-of-band.

**Substrate isolation**

- **FR-018**: The retrieval/index engine (FTS5, sqlite-vec, embedding providers, converters) MUST be confined to infrastructure. Domain and application layers MUST NOT import index/engine types directly; interaction is via the shared retrieval port. mem0, chroma, and LlamaIndex MUST NOT be imported anywhere.

**Migration**

- **FR-019**: This branch is unreleased; there is **no data migration**. A single migration MUST drop `memory_records` and create the fresh unified schema. Legacy on-disk engine directories (chroma/LlamaIndex) from pre-release builds are abandoned in place — nothing reads them — rather than deleted. Old mem0/chroma text is not migrated.

### Key Entities

- **Memory Store** (a resource of kind `memory`): one store per scope — the global store (sentinel ULID) or a per-project store (project ULID). Config holds enabled retrieval modes, embedding config, and `max_fact_chars`.
- **Memory Fact** (one markdown file = one `documents` row): `id`, `name`, `description`, body, `metadata` (`type`, `actor`, `origin_session_id`), `path` (absolute `.md` path), `content_sha256`, `created_at`, `updated_at`. The markdown file is the source of truth. Read responses additionally surface the containing folder's absolute path so the UI can open/reveal/copy it.
- **Memory Hit** (recall result, not persisted): `id`, `text`/passage, `score`, `source`, `time`.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A fact written by one agent via `coffer__remember` is recalled by a different agent via `coffer__recall` in the same project within one session, with no per-agent copy diverging.
- **SC-003**: With 200 facts in a scope, recall latency for a typical keyword query is ≤ 300 ms wall-clock on a developer laptop.
- **SC-004**: Default retrieval works offline with zero configuration (keyword + grep); vector recall is opt-in and degrades to keyword (flagged) when unconfigured — it never errors.
- **SC-006**: Every Acceptance Scenario is covered by at least one test marked `acceptance(spec="007-memory", scenario="…")`.
- **SC-007**: Substrate isolation is enforced by importlinter: no module under `coffer.application.*` or `coffer.domain.*` imports the index engine, and `mem0`/`chroma`/`llama_index` are imported nowhere.
- **SC-008**: `make verify` passes locally and in CI.

## Assumptions

- The user runs Coffer on their own machine; memory data stays local. Calling a configured cloud embedding provider for opt-in vector recall is allowed (local-first ≠ no remote API calls).
- The canonical format is per-fact markdown files (YAML frontmatter + body) plus a regenerated `MEMORY.md` index.
- The coffer-mcp-shim propagates its launch cwd to the daemon at session handshake on the supported agents (to verify in implementation).
- The knowledge base (spec 006) and memory share one unified substrate (`documents` table discriminated by `kind` + JSON `metadata`); they are two faces, not duplicated code.
- Single-user concurrency is small.
