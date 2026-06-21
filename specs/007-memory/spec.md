# Feature Specification: Memory (Shared Agent Memory)

> 中文版: [spec.zh.md](./spec.zh.md)

**Feature Branch**: `feature/kb-memory-redesign`
**Created**: 2026-05-22
**Status**: Accepted (redesign — in development)
**Input**: Redesign of Coffer's memory feature — the **memory face** of one unified substrate shared with the knowledge base (spec 006). Memory is no longer a mem0 vector store with an LLM at write time; it becomes a **single shared source of truth across agents** (no divergent per-agent copies). Canonical storage is per-item markdown files under a per-scope `knowledge/` lane (freshly-remembered items in `knowledge/inbox/`) under `~/.coffer/memory/`, with a two-layer scope (global + per-project) and **no derived index file** (the prior `MEMORY.md` projection is removed — read by nothing in retrieval). Agents read and write memory **only through Coffer's MCP gateway** (`coffer__recall`/`remember`/`list_memory`); editing and deleting are user surfaces (REST/CLI/external editor), not MCP tools. Coffer keeps its own canonical format and does not touch agents' native memory files (native projection was removed — see ADR-026). The user does full CRUD in the Coffer UI. Retrieval uses the same engine as the knowledge base (grep / keyword FTS5+BM25 / vector sqlite-vec). See [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md) for the full design rationale.

## User Scenarios & Testing

### User Story 1 — One memory, every agent (Priority: P1)

The developer works on a project with Claude Code in the morning and Codex in the afternoon. While using Claude Code the agent learns "this repo deploys via `make release`, never `git push --tags` directly" and records it through Coffer's `coffer__remember` tool. In the afternoon, Codex — a different agent — recalls the same fact because both agents read and write **one shared store**. No copy diverges.

**Why this priority**: This is the core of the redesign. A per-agent silo that drifts across agents is the problem being solved; without a single shared source of truth there is no feature.

**Independent Test**: From a fresh install, run an MCP client in a git project, call `coffer__remember` with a project fact, then from a second MCP client (different agent identity) in the same project call `coffer__recall` and observe the fact returned. Confirm the same fact appears as a per-item markdown file under the project store's `knowledge/inbox/` lane.

**Covering scenarios**:

- agent remembers a project fact
- agent recalls a project fact
- recall spans project and global scope
- remembered items are stored in the knowledge lane
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

The developer wants to see and correct what agents remember: browse facts per scope in a **read-only** viewer, then fix one that drifted **in their own external editor** (or via the API/CLI), add a fact by hand, delete a wrong one. The Coffer UI never edits fact content in-app; instead each fact and its containing folder offer "open in external editor" and "reveal in file manager" (daemon-backed on the web, native on the desktop), and any out-of-band correction is picked up by the existing lazy reindex-on-read (FR-010).

**Why this priority**: Memory without human curation is uncomfortable; agents sometimes record wrong things. Curation makes the feature safe to leave on — and routing edits through the user's own editor keeps the markdown files the sole source of truth without a second editing surface to keep in sync.

**Independent Test**: After agents have written facts, open the memory view (read-only) and confirm fact content renders but is not editable in-app. Open one fact in an external editor (or `coffer memory edit`/PATCH), correct its text outside Coffer, and observe the next `recall` returns the corrected version (lazy reindex-on-read). Add a fact (actor=user) via the CLI/API, then delete a different one and observe it gone from disk and recall.

**Covering scenarios**:

- user adds a fact
- user corrects a fact out-of-band
- user deletes a fact
- read-only viewer offers open/reveal affordances

---

### User Story 6 — Distil insights from an agent's past conversations into shared memory (Priority: P2)

The developer has been working on a project with Claude Code for weeks. Many
engineering decisions, failed approaches, and project conventions were
discussed and settled in those sessions, but never explicitly recorded as
memory facts. The developer runs `coffer transcript distill claude_code
--project /repo` (or clicks "Distil to memory" in the Coffer UI). Coffer
reads the local `.jsonl` transcript files, scrubs tool payloads and secrets,
asks an LLM to extract durable insights, and appends them as project-scoped
**journal** entries (episodic memory). From that point on, any agent — including
Codex on a second machine — can recall those entries through `coffer__recall`
(the journal lane participates in recall, FR-043), because memory is shared
(Spec 007) and synced (Spec 010). No raw transcript content is ever stored or
transmitted. When the transcript's working directory resolves to a git project,
the insights are appended to that project's journal; a session whose path is not
inside a git work-tree is skipped — there is no global journal.

**Why this priority**: Agents accumulate institutional knowledge in local
transcripts that is otherwise siloed per-session and inaccessible to other
agents. Distillation is the least-invasive mechanism to surface that
knowledge: it produces journal entries, inheriting cross-agent sharing
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
that at least one distilled **journal entry** is now retrievable and contains no
tool payloads, file contents, or secret-like strings (the `journal_append` audit
records the writing actor; the episodic entry text carries no frontmatter).

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

- **Vector unavailable but embedding unconfigured**: when the store's resolved strategy needs vectors but no embedding provider is configured, `recall` falls back to keyword internally and returns results; it never blocks. The fallback is NOT surfaced as a query-time response flag. Default retrieval is keyword+grep (zero config, offline).
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
- **Then** a per-item markdown file (YAML frontmatter `name`/`description`/`metadata.type`/`origin_session_id` + body) is written under the project memory dir's `knowledge/inbox/` subdir, the file is indexed into `documents`, and an audit entry is recorded.

### Scenario: agent recalls a project fact

- **Given** a project memory store with facts,
- **When** an MCP client calls `coffer__recall` with a query,
- **Then** ranked facts are returned with id, text, score, source, and time, after a lazy reindex scan of the fact dir picks up any out-of-band deltas.

### Scenario: recall spans project and global scope

- **Given** facts exist at both global and project scope,
- **When** an MCP client calls `coffer__recall` without a scope,
- **Then** results are drawn from both the project store and the global (sentinel) store.

### Scenario: remembered items are stored in the knowledge lane

- **Given** an MCP client running inside a git project,
- **When** it calls `coffer__remember` with a fact,
- **Then** the item is written as a markdown file under the project store's `knowledge/inbox/` subdir (never at the store root and with no `MEMORY.md` generated), it is indexed into `documents`, and a subsequent `coffer__recall` returns it.

### Scenario: remember at global scope

- **Given** an MCP client,
- **When** it calls `coffer__remember` with `scope=global`,
- **Then** the fact is written to the global store keyed by `project_id = WORKSPACE_GLOBAL_PROJECT_ID` and recall from any project returns it.

### Scenario: project scope resolves from the agent's working directory

- **Given** the coffer-mcp-shim reports its launch cwd at session handshake,
- **When** the daemon resolves the project memory store,
- **Then** it computes the git-root of that cwd and resolves (lazily provisioning if absent) the per-project store keyed by that project's ULID.

### Scenario: out-of-band fact-file edits are visible on recall

- **Given** a project memory store with facts,
- **When** a fact file is edited out-of-band directly on disk (frontmatter preserved),
- **Then** the next `coffer__recall` returns the edited content (lazy reindex-on-read), with no filesystem watcher running.

### Scenario: user adds a fact

- **Given** a memory store,
- **When** the user adds a fact via the Coffer UI or CLI,
- **Then** the canonical markdown is written under the store's `knowledge/inbox/` subdir with `metadata.actor = "user"`, the document is indexed, and an audit entry is recorded.

### Scenario: user corrects a fact out-of-band

- **Given** a fact exists,
- **When** the user corrects its text outside the in-app viewer — via the REST/CLI write surface (`PATCH …/facts/{id}` / `coffer memory edit`) or by editing the canonical markdown directly in an external editor,
- **Then** the canonical markdown is rewritten, the document is reindexed (immediately for the REST/CLI path; on the next `recall` via lazy reindex-on-read for a direct file edit), and recall reflects the new text.

### Scenario: user deletes a fact

- **Given** a fact exists,
- **When** the user deletes it,
- **Then** the markdown file and its index rows are removed, and recall no longer returns it.

### Scenario: read-only viewer offers open/reveal affordances

- **Given** a fact viewed in the Coffer UI,
- **When** the user inspects the fact (and its containing folder),
- **Then** the content renders read-only (no in-app content editing), the read responses surface the fact's absolute on-disk `.md` path and its containing folder's absolute path, and the UI offers "open in external editor" + "reveal in file manager" for both the file and the folder on **both** surfaces — desktop (Tauri) via the OS opener, web via the loopback daemon (spec 004 FR-039) — with no copy-path fallback; which editor opens is decided by the global preferred-editor preference (see 002-ui-shell).

### Scenario: clear a memory scope

- **Given** a memory store with facts,
- **When** the user clears that scope,
- **Then** every memory item under `knowledge/` is removed and its index rows dropped, but the store Resource is preserved.

### Scenario: user renames a memory store

- **Given** a memory store (e.g. one whose originating folder was never recorded, so it would otherwise show as `project-<ULID>`),
- **When** the user sets a display label via `PATCH /memory_stores/{name}/label`,
- **Then** the label is trimmed, echoed back, surfaced on the store read + list as the readable name, and an empty / whitespace label clears it (reverting to the FR-017a derivation); renaming an unknown store is a 404, not an autocreate.

### Scenario: built-in memory tools appear in client tool list

- **Given** an MCP client connects to coffer's gateway,
- **When** the client lists tools,
- **Then** `coffer__recall`, `coffer__remember`, `coffer__list_memory`, `coffer__set_handoff`, and `coffer__resume` appear alongside other built-in and upstream tools.

### Scenario: vector recall falls back when embedding is unconfigured

- **Given** a memory store with no embedding provider configured,
- **When** the engine resolves to a vector strategy but no embedder is available,
- **Then** the call runs a keyword search instead and returns results with no error; the degradation is NOT surfaced as a query-time response flag (the internal keyword fallback, like the KB face).

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
  the LLM call, the LLM returns structured insights (each just `name` /
  `description` / `body` — distillation does NOT classify a per-insight type),
  and each insight is **appended as a project-scoped journal entry** (episodic
  memory, `actor="agent"` recorded in the `journal_append` audit) — never a flat
  knowledge fact; a session whose path is not inside a git project is skipped
  (there is no global journal); no raw transcript content appears in any
  persisted entry; `coffer__recall` subsequently returns the new journal entries
  (FR-043); and when `dry_run=true`, insights are returned but nothing is written
  to disk.

### Scenario: browse an agent's transcript history with title, search, and sort

- **Given** a registered agent with several local transcript sessions across
  more than one project,
- **When** `GET /api/v1/agents/{name}/transcripts` is called with a search
  query, a project filter, and a sort key (`started_at` or `last_activity_at`),
- **Then** each returned session summary carries a derived title, message count,
  `started_at`, `last_activity_at`, and the session file's absolute source path;
  only sessions whose title or project path matches the search and whose project
  matches the filter are returned, ordered by the requested sort key and
  direction, and paged by `limit`/`offset` alongside the matched total.

### Scenario: the organizer drains the inbox into a topic document

- **Given** a memory store with two freshly-remembered items in its
  `knowledge/inbox/` and an internal model configured,
- **When** `POST /api/v1/memory_stores/{name}/organize` (or `coffer memory
  organize <name>`) is called,
- **Then** the internal LLM organizer drains the inbox (no items remain), at
  least one `knowledge/<topic>.md` topic document exists holding the merged
  content, `knowledge/INDEX.md` lists that topic, a `memory_organized` audit
  entry is recorded, and a subsequent `recall` returns content from the topic
  document (not the now-empty inbox).

### Scenario: organizing merges a note into an existing topic without clobbering it

- **Given** a memory store that already has a hand-edited topic document
  containing content X plus a new related item in its `knowledge/inbox/`,
- **When** `organize` is called and the organizer merges the new item into that
  topic,
- **Then** the topic document still contains the original content X alongside
  the newly integrated information, the inbox item has been removed, and the
  consolidation changelog (`consolidation-log.md`) records the merge — the
  organizer never regenerates from scratch and never clobbers a human edit.

### Scenario: organize is a no-op when no internal model is configured

- **Given** a memory store with items in its `knowledge/inbox/` but no internal
  model configured,
- **When** `organize` is called,
- **Then** the call returns `status="no_model"`, the inbox is left untouched, no
  topic document is written, and no error is raised.

### Scenario: a topic document recalls at passage granularity

- **Given** an organized memory store whose `knowledge/` lane holds a topic
  document with two distinct heading sections, each describing a different
  subject, indexed for recall,
- **When** `coffer__recall` is queried with terms that occur only in the second
  section,
- **Then** the returned hit's text is that section's **passage** — not the whole
  document — so the first section's distinctive wording does not appear in the
  hit, confirming topic documents are chunked **per passage** (heading- and
  block-structure aware) rather than one chunk per file.

### Scenario: the reorg pass consolidates duplicate topic documents

- **Given** a memory store with two overlapping topic documents (both about the
  same subject, one carrying extra detail) and an internal model configured,
- **When** `POST /api/v1/memory_stores/{name}/reorg` (or `coffer memory reorg <name>`)
  runs and the internal agentic loop reads both documents, writes the merged
  content into one, and supersedes the now-redundant other,
- **Then** a single topic document holds the combined content, the redundant
  document no longer appears in `recall` or `INDEX.md`, a subsequent `recall`
  returns the merged content, and a `memory_reorganized` audit entry is recorded.

### Scenario: reorg never destroys content — a superseded topic stays recoverable

- **Given** a memory store with a topic document holding content X (possibly a
  human edit),
- **When** the reorg loop overwrites or supersedes that document,
- **Then** the prior content X is first archived to the store's `superseded/`
  tombstone (so it is **recoverable**, never hard-deleted), the tombstone is
  **excluded from recall** (it lives outside the `knowledge/` lane), and the
  consolidation changelog records the supersession — the loop is an incremental
  edit, never a from-scratch regeneration.

### Scenario: reorg is a no-op when no internal model is configured

- **Given** a memory store with topic documents but no internal model configured,
- **When** `reorg` is called,
- **Then** the call returns `status="no_model"`, no topic document is written,
  superseded, or archived, and no error is raised.

### Scenario: memory is auto-organized after the store goes idle

- **Given** the opt-in auto-organize trigger is enabled, an internal model is
  configured, and an item is freshly remembered into a store's `knowledge/inbox/`,
- **When** the store goes idle (no further memory writes) for the conservative
  debounce delay,
- **Then** the organizer runs **automatically in the background** — with no
  explicit `organize` call — draining the inbox into a topic document, and the
  background pass never blocks: cancelling the pending trigger (e.g. at daemon
  shutdown) before it fires simply leaves the inbox intact for a later pass.

### Scenario: the organizer routes a rule-shaped note into the rules lane

- **Given** a memory store with an internal model configured and two freshly
  remembered inbox items — one a behavioural rule ("always run the verify step
  before pushing") and one an ordinary fact,
- **When** `organize` runs and the organizer classifies the first item as a rule
  and the second as ordinary knowledge,
- **Then** the rule is appended to the store's procedural `rules/rules.md` lane
  (not written into a `knowledge/<topic>.md` doc), the ordinary fact becomes a
  topic document, both inbox items are drained, and `recall` does NOT surface the
  rule (the `rules/` lane sits outside the `knowledge/` recall glob, like
  `handoff/` and `superseded/`).

### Scenario: the rules read surface returns the stored rules

- **Given** a memory store whose `rules/rules.md` holds one or more rules,
- **When** `GET /api/v1/memory_stores/{name}/rules` (or `coffer memory rules <name>`)
  is called,
- **Then** the response returns the rules text verbatim (the surface that a
  later session-start injection reads), and a store with no rules returns an
  empty/`null` body rather than an error.

> **Deferred to future test work** (tests land with the e2e infrastructure; `make verify-acceptance` does not gate on them): desktop memory list view per scope, the desktop read-only fact viewer's open-in-editor / reveal affordances, CLI `coffer memory …` end-to-end with a running daemon, per-store metrics (HTTP route).

## Requirements

### Functional Requirements

**Storage & scope**

- **FR-001**: System MUST store every memory item as a per-item markdown file (YAML frontmatter `name`/`description`/`metadata.type`/`metadata.actor`/`origin_session_id` + body) under a per-scope **`knowledge/` lane** — freshly-remembered items in `knowledge/inbox/`, organized topic documents (`knowledge/<topic>.md`) plus an `INDEX.md` maintained by the consolidation organizer (a later memory PR). The markdown files are the **sole source of truth**; SQLite is a rebuildable index. **No `MEMORY.md` index is generated** (the prior derived index was a vestigial projection artifact, read by nothing in retrieval).
- **FR-002**: System MUST support two memory scopes: **global** (one store keyed by `project_id = WORKSPACE_GLOBAL_PROJECT_ID`, the existing sentinel `00000000000000000000000000`) and **per-project** (one store per project, keyed by the project's ULID), stored under `~/.coffer/memory/global/knowledge/` and `~/.coffer/memory/projects/<project-ulid>/knowledge/` respectively.
- **FR-003**: `coffer__remember` (and a user add) MUST append a memory item to the per-scope inbox (`knowledge/inbox/`) with no LLM at write time; organization into topic documents is performed asynchronously by the consolidation organizer (a later memory PR) and never blocks the write or `recall`.
- **FR-004**: System MUST resolve the per-project store from the agent's reported launch cwd at session handshake: the daemon computes the git-root and resolves — lazily provisioning if absent — the store for that project's ULID.

**Fact lifecycle**

- **FR-005**: Agents and users MUST be able to write a fact directly (no LLM at write time). Fact text MUST be at least 1 char and at most `max_fact_chars` (default 8192); empty or over-long text is rejected at the API boundary with nothing persisted.
- **FR-006**: Users and agents MUST be able to list facts (per scope), get a single fact by id, edit a fact's text, delete a single fact, and clear all facts in a scope. Fact **edit/delete** is via the REST/CLI write surface (`PATCH/DELETE …/facts/{id}` / `coffer memory edit/delete`) and external-editor files-as-truth — the Coffer UI renders fact content read-only and does not edit it in-app; the MCP `update_memory`/`forget` tools are **removed** (the agent's write surface is `remember` + the internal organizer). Clearing preserves the store Resource.
- **FR-007**: Every fact carries `metadata.actor` (`agent` | `user`) and an optional `metadata.type` (e.g. `project` / `feedback` / `reference` / `user`); the writer sets these.

**Retrieval**

- **FR-008**: Recall MUST use the unified retrieval engine shared with the knowledge base: `grep` (ripgrep over the store's fact files; essential for content FTS5 cannot tokenize, e.g. CJK), `keyword` (FTS5 BM25, the default), and `vector` (sqlite-vec with a configurable embedding provider). These engine modes are an **internal detail** — recall does NOT take an external `mode`; the engine resolves the store's default strategy automatically. When the resolved strategy needs vectors but no embedding provider is configured, recall MUST fall back to `keyword` internally — never block, and the fallback is NOT surfaced as a query-time response flag (the `fallback` field is removed from the recall response).
- **FR-009**: `coffer__recall` MUST default to spanning both the project and global stores (an explicit `scope` narrows recall to one store: `project` = the project store only, `global` = the global store only); cross-store results are merged by reciprocal rank fusion (per-store scores are not comparable across modes/stores; each hit keeps its per-store score, only the merged order comes from the fusion). Results carry id, text, score, source, and time — `time` is the fact's `updated_at` and `source` is `<scope>:<fact file path>`. Default `top_k` is 5; callers MAY specify 1–20.
- **FR-010**: Memory MUST use **lazy reindex-on-read**: `recall` first scans the fact directory for deltas (added/changed/removed files by content hash) and reconciles the index before searching, so out-of-band edits — a human's corrections made in their own external editor, or any direct on-disk edit — are visible immediately with no filesystem watcher. This is the mechanism that makes external corrections appear, so the UI can stay a read-only viewer (FR-017) while curation happens in the user's editor.

**Agent integration via MCP**

- **FR-015**: Coffer's MCP gateway MUST expose built-in tools `coffer__recall(query, scope?, top_k?)` (no `mode` parameter — retrieval mode is internal), `coffer__remember(text, scope?, type?)`, `coffer__list_memory(scope?)`, `coffer__set_handoff(body)`, and `coffer__resume()`, namespaced under the reserved `coffer__` prefix. `remember` defaults to `scope=project`; `recall` defaults to both scopes. There is no MCP `update_memory`/`forget` tool — fact edit/delete is a user surface (REST/CLI/external editor), per FR-006.
- **FR-016**: Built-in memory tool invocations MUST share the existing invocation-logging surface (one `mcp_invocations` row: tool name + who/when/duration/outcome only — no arguments or returned content).

**Working-state handoff (continuity)**

- **FR-023**: The system MUST provide a **working-state handoff** lane keyed by **(project store × git branch)**: one file per branch under `~/.coffer/memory/projects/<project-ulid>/handoff/<branch-slug>.md`, with YAML frontmatter (`branch`, `updated_at`) plus a freeform markdown body. The branch is resolved from the agent's reported cwd (its repo's current branch). Handoff is **per-project only** — there is no global handoff.
- **FR-024**: `coffer__set_handoff(body)` MUST **overwrite** the current branch's handoff file (no accumulation; one scene per branch), set `updated_at`, and record a `handoff_set` audit entry. The handoff body is files-as-truth on disk (it rides the git sync mirror like other memory files) and MUST NOT be returned by `coffer__recall` (it lives in the `handoff/` subdir, outside the recall glob).
- **FR-025**: `coffer__resume()` MUST return the current branch's saved handoff — `found=true` with `branch`, `body`, `updated_at`, and a freshness `note` annotating that the scene may be stale — or `found=false` when no handoff exists for the branch (a fresh branch) or the cwd is not inside a git project. It MUST never error on a missing handoff and MUST NOT fabricate content.
- **FR-026**: When the agent's cwd does not resolve to a git project (no project scope, no branch), `coffer__set_handoff` MUST be rejected (there is no store to write to and no global handoff) and `coffer__resume` MUST return `found=false`.

**Consolidation — the internal organizer**

- **FR-027**: The system MUST provide an **internal memory organizer** that, on an **explicit trigger only** (`POST /api/v1/memory_stores/{name}/organize` and `coffer memory organize <name>`; no automatic/background firing in this PR), drains a store's `knowledge/inbox/` of freshly-remembered items into a small set of coherent **topic documents** (`knowledge/<topic-slug>.md`, YAML frontmatter `title`/`description`/`updated_at` + a markdown body) using Coffer's **internal LLM connection** (the connection marked internal-default; configured on Settings → LLM Connections, spec 011) via a **one-shot completion per item** — never an agent-facing tool. The organizer MUST process items sequentially, and one item's LLM/parse failure MUST NOT abort the run (the other items still organize).
- **FR-028**: For each inbox item the organizer MUST (a) retrieve up to the top-K (K=3) most-relevant **existing topic docs** via the shared retrieval engine (no LLM on this step) as merge candidates, (b) make **one LLM call** that either MERGES the item into the best-fitting candidate — **preserving all existing content and human edits**, integrating the new information, removing exact duplicates — or CREATES a new topic when none fits, and (c) write the returned full document body to `knowledge/<topic-slug>.md`. The organizer MUST be an **incremental merge into the existing document, never a from-scratch regeneration**: the LLM is given the full existing topic content to merge into, so human corrections survive. The organizer MUST NOT hard-delete an existing topic doc (it only creates or overwrites with merged content; git history is the audit trail).
- **FR-029**: An inbox item MUST be **deleted only after** its content is successfully written into a topic doc. A malformed or unparseable LLM response (missing/empty required keys, an unsafe `topic_slug`, or non-JSON) MUST cause that item to be **skipped** — left in the inbox, no topic doc written or corrupted — and the run continues; the result reports the count of skipped items. `organize` on an empty inbox is a no-op (`status="empty"`); when no internal connection is configured `organize` is a clean no-op (`status="no_model"`, inbox untouched, nothing written) rather than an error.
- **FR-030**: After draining, the organizer MUST regenerate the store's `knowledge/INDEX.md` review catalog from all topic docs' frontmatter (`- [<title>](<slug>.md) — <description>`), reconcile the index (dropping the removed inbox rows and (re)indexing the new/updated topic docs so `recall` returns content from the topic docs, not the drained inbox), and record one `memory_organized` audit entry (store + counts only — no item content). `recall` MUST surface organized topic-doc content and MUST NOT surface `INDEX.md`.
- **FR-031**: The organizer MUST keep a **non-blocking consolidation changelog** at the store ROOT (`<store>/consolidation-log.md`, append-only, human-readable: one line per merged/created topic with the timestamp and the source inbox item). The changelog is auditable, never a gate, and is **excluded from recall** (it lives outside the `knowledge/` lane) and **from the sync mirror** (machine-local, like `INDEX.md`; topic docs themselves DO sync as source-of-truth).
- **FR-032**: The memory reconciler MUST chunk a fact file's body into **passage-granular, structure-aware chunks** using the retrieval substrate's shared markdown chunker (`infrastructure/knowledge/chunking.chunk_markdown` — splits on heading sections, keeps fenced code / tables atomic, and packs structural blocks up to a fixed window), with **fixed memory chunk-size/overlap parameters** (not a per-store `MemoryStoreConfig` field), so a multi-section organized topic document surfaces the **most relevant passage** on `recall` rather than its entire body as a single chunk. A short single-passage fact (e.g. an inbox item) still chunks to one passage — so this changes only the **granularity** of large/organized topic docs, never *what* `recall` includes or excludes: the `INDEX.md`, inbox-vs-topic, and `handoff/` recall isolation (FR-024/030/031) and the legacy-root-fact abandonment (FR-019) are all unchanged.
- **FR-033**: The system MUST provide an **internal agentic reorganization pass** that, on an **explicit trigger only** (`POST /api/v1/memory_stores/{name}/reorg` and `coffer memory reorg <name>`; no automatic/background firing in this PR), runs a bounded **langgraph `create_react_agent` loop** driven by Coffer's **internal LLM connection** (the connection marked internal-default; configured on Settings → LLM Connections, spec 011) over the store's existing topic documents to keep them coherent — consolidating duplicate/overlapping documents and splitting over-long ones. The loop is given a small, fixed tool surface over the topic docs only — **list** topics, **read** a topic, **write** (create/overwrite) a topic, and **supersede** (retire) a topic — and is **never an agent-facing tool** (it is internal, like the organizer). The langchain/langgraph code MUST stay confined to `infrastructure.chat` (importlinter Contract 9); `application/memory` reaches it only through an injected memory-local port. When no internal connection is configured the pass is a clean no-op (`status="no_model"`, nothing written/superseded/archived) rather than an error; a store with no topic documents is likewise a no-op (`status="empty"`). After the loop the pass MUST regenerate `INDEX.md`, reconcile the index (so `recall` reflects the consolidated docs), and record one `memory_reorganized` audit entry (store + counts only — no document content).
- **FR-034**: The reorg pass MUST be **non-destructive and incremental — it MUST NOT hard-delete or from-scratch-regenerate a topic document**. Every mutation that removes or replaces existing topic-doc content MUST first **archive the current version** to the store-root `superseded/` tombstone (`<store>/superseded/<slug>-<timestamp>.md`): a `write` that overwrites an existing topic archives the prior version before writing the new one, and a `supersede` **moves** the document there (it is never unlinked into the void). The `superseded/` tombstone is **excluded from recall** (it lives outside the `knowledge/` lane, like `handoff/` and `consolidation-log.md`) and **DOES sync** as recoverable source-of-truth history (unlike the machine-local `INDEX.md`/changelog). Topic-doc writes remain **atomic**, and every write/supersede is appended to the `consolidation-log.md` changelog. This is the data-loss guarantee: no byte ever leaves the `knowledge/` lane without first being recoverably archived, so a human edit can never be irrecoverably clobbered.
- **FR-035**: The system MUST provide an **auto session-end organize trigger** that fires the `organize` pass (FR-027) **automatically, in the background, when a memory store goes idle** — approximating "session end" without a per-agent disconnect signal. It is driven by the memory write-notify hook: each memory write (re)arms a single **debounced** timer; after the configured idle delay elapses with no further writes, the organizer runs for the changed store(s) as a background task. The trigger MUST be **conservative and non-blocking**: (a) it is **opt-in**, controlled by an environment switch and **default-OFF** (so it never makes a surprise internal-LLM call), mirroring the optional auto-backup worker; (b) the background pass MUST NEVER block or break daemon shutdown — on shutdown any pending timer is **cancelled** (the un-fired inbox is simply left intact for a later idle pass or an explicit trigger; nothing is lost, since `recall` already covers the inbox and `organize` is idempotent); (c) a background-pass failure MUST be suppressed + logged, never surfacing to a writer or aborting the daemon; (d) when no internal connection is configured the pass is a clean no-op (FR-027). It introduces **no new REST/CLI surface** (it is an internal trigger over the existing organizer) and reuses the `memory_organized` audit. The langchain/langgraph confinement (Contract 9) is unchanged: the trigger lives in `application`/`surfaces` and reaches the LLM only through the already-wired organizer.
- **FR-036**: The system MUST provide a **procedural `rules` lane** — a single `rules/rules.md` per memory store (global + per-project), holding "do this / don't do that" behavioural rules. The rules lane is **agent-written via the organizer's classification, never an explicit agent param**: during `organize` (FR-027/028), the organizer's single per-item LLM call MAY additionally classify an inbox item as a **rule**; a rule item is **appended** to `rules/rules.md` (the inbox item is drained only after the append succeeds) instead of being merged into a `knowledge/<topic>.md` topic document, and the `organize` result/audit reports a `rules_appended` count. The `rules/` lane sits at the store ROOT (a sibling of `knowledge/`, like `handoff/` and `superseded/`) so it is **excluded from `recall`** for free (the recall glob and the reconciler only descend into `knowledge/`; the grep guard keeps only `knowledge/` hits) — rules are **delivered by ambient session-start injection, not by `recall`**. The lane is **source-of-truth and DOES sync** (like `handoff/`/topic docs; it is not a derived/machine-local file). The system MUST expose the stored rules read-only for the injection surface: `GET /api/v1/memory_stores/{name}/rules` and `coffer memory rules <name>` return the rules text (an empty/`null` body when there are no rules, never an error). The **session-start injection** that delivers these rules into each managed agent as context (ADR-026: injection only, never a native file write) is a **separate later slice (PR3b)** — this slice lands the lane, the classification, and the read surface.

**Journal lane (episodic)**

### Journal lane (episodic)

- **FR-040:** Coffer SHALL provide a per-project `journal` lane that stores episodic events as append-only, time-partitioned markdown files (`projects/<ulid>/journal/<YYYY-MM>.md`). There is NO global journal.
- **FR-041:** Journal files SHALL be included in the sync mirror as source-of-truth history (like `rules/` and `superseded/`). Unlike `rules/` and `handoff/`, the journal lane also participates in `recall` (FR-043).
- **FR-042:** Coffer SHALL expose internal `JournalService.append(cwd, body, actor)` and `read_recent(cwd, limit)`. Appending outside a git project raises `ScopeUnresolved`; reading outside a git project returns an empty list. `read_recent` returns the newest entries first, capped at `limit`; `limit=0` returns an empty list (no implicit "all"). The `journal_append` audit entry records `char_size` only — never the body.
- **FR-043:** The journal lane SHALL participate in `recall`. The memory reconciler MUST scan each `journal/<YYYY-MM>.md` file and index it as one memory document (`kind=memory`), chunked with the same shared markdown chunker and fixed parameters as topic docs (FR-032), covered by lazy reindex-on-read (FR-010) so an out-of-band edit or a fresh `JournalService.append` becomes searchable on the next `recall`. The grep recall guard (which keeps only `knowledge/` hits) MUST additionally keep `journal/` hits, parsing them per journal file rather than as fact files. Journal documents MUST NOT count toward a store's `fact_count` (which counts only the `knowledge/` lane). The `rules/`, `handoff/`, and `superseded/` lanes remain excluded from `recall`.
- **FR-044:** A `recall` hit from the journal lane MUST be distinguishable from a `knowledge/` hit: like every recall hit its `source` carries the on-disk path of the matched file (per FR-022), and a journal hit's path is the `journal/<YYYY-MM>.md` file (containing the `journal/` lane segment), so the agent can tell episodic events from semantic facts.
- **FR-045:** Transcript distillation (User Story 6) SHALL write each extracted insight to the **journal** lane (episodic), NOT as a flat `knowledge/` fact. Distillation stays "dumb": it extracts `name` / `description` / `body` only and MUST NOT classify a per-insight type — the legacy `InsightType` (`decision` / `gotcha` / `convention` / `todo`) is retired (no `type` field on the distilled insight, the distill prompt, or the distill response). Each insight is appended via `JournalService.append` to the session's project journal; a session whose path does not resolve to a git project is skipped (there is no global journal). The distill response reports the written journal entries (the `fact_ids` field is renamed `journal_entries`). Promotion of recurring journal patterns into `knowledge`/`rules` is the organizer's job (a later consolidation slice), never distillation's.
- **FR-046:** Memory recording MUST be **automatic**, not dependent on a human running `coffer transcript distill`. The system SHALL run an **auto-distill catch-up sweep** — a background worker that, on daemon start and then periodically, scans each managed agent's transcript sessions and distills any **settled, not-yet-distilled** session into the journal lane (FR-045). A session is eligible only when its `last_activity_at` is (a) **settled** (older than a settle threshold — never an in-progress session) and (b) within a **recency window** (a catch-up net for recently-missed sessions, NOT a full historical backfill); each pass distills at most a bounded number of sessions (the remainder catch up on later passes, logged). Distilled sessions are tracked by `(agent, session_id, content_sha256)` in a machine-local ledger so a session is **never double-distilled** (re-distilled only if its content materially changed); this ledger is the idempotency key the future SessionEnd hook (slice 6) shares. The sweep is **default-ON** (it is the write guarantee) with an environment off-switch; it is **non-blocking and failure-suppressed** (one session's LLM/parse failure never aborts the sweep or the daemon, mirroring FR-035), a clean **no-op when no internal connection is configured**, and on shutdown the worker stops without firing. It introduces **no new REST/CLI surface** and reuses the FR-045 distill path + journal lane. (The immediate-on-close SessionEnd hook is slice 6; this sweep is the standalone guarantee.)

**Transcript history**

- **FR-037**: The transcript reader MUST parse each supported agent's *real* on-disk session format. **Codex** rollout files (`~/.codex/sessions/**/*.jsonl`) wrap every event in a `payload` envelope: the working directory and session id come from `session_meta.payload.cwd`/`payload.id`, and conversation turns are `response_item` events whose `payload.type == "message"` (role + typed `*_text` content blocks). The reader MUST count turns from these `response_item` messages only — the parallel `event_msg` `user_message`/`agent_message` UI events MUST NOT be double-counted — and MUST stay defensive (skip unrecognised / non-JSON lines, never raise on one bad line). **Claude Code**'s flat top-level format is unchanged. (Before this slice the Codex parser read top-level fields the real format never carries, so every Codex session listed as 0 messages with no project.)
- **FR-038**: Each transcript session summary MUST carry a human-readable **title**, a **last-activity timestamp** (`last_activity_at`), and the session file's absolute **source path**. The title is the agent's own session title when present (Claude Code's `ai-title`, latest wins) and otherwise the first *real* user message — skipping non-conversational preambles (environment/instructions blocks, shell-command echoes, slash commands) — truncated to a single line; it MAY be null when none can be derived. `started_at` is the first event timestamp and `last_activity_at` the last. The source path powers a read-only "reveal in file manager" affordance via the shared `FileActions` component (desktop reveal / web copy-path), mirroring FR-021/FR-022 for memory facts — no new backend open/reveal endpoint is introduced.
- **FR-039**: The transcript list surface (`GET /api/v1/agents/{name}/transcripts`) MUST expose **all** of an agent's sessions (not only a recent window) with server-side **search** (a query matched against the title or project path), **filtering** (by exact project path and by a `started_at` time range), and **sorting** (by `started_at`, `last_activity_at`, or `message_count`, ascending or descending), paged via `limit`/`offset` and returning the matched `total`. The reader MUST back this with an in-process, mtime-aware cache so repeat listings of an agent with thousands of sessions stay responsive — a session file is re-parsed only when its mtime changes.

**Surfaces**

- **FR-017**: Users MUST be able to perform full memory CRUD through the programmatic write surfaces — (a) a REST API under `/api/v1/memory_stores/` and (b) `coffer memory …` subcommands. (The REST write endpoints are also what agents author facts through via the MCP gateway.) User writes set `metadata.actor = "user"`, write the canonical markdown under the store's `knowledge/inbox/` subdir, reindex, and audit. The desktop/web UI surfaces facts **read-only** (it does not edit fact content in-app); humans curate by editing the canonical markdown in their own external editor (picked up by lazy reindex-on-read, FR-010) or via the REST/CLI write surface. The read-only viewer MUST render fact content at a comfortable reading **max-width** (centered), and the detail-page fact **list** MUST be a single **scrollable** list with **no in-UI page-based pager** (the UI fetches one page at the max `limit`; the facts **API** stays paginated by `limit`/`offset`). Store names on these surfaces are validated: only `global` or `project-<26-char ULID>` are legal — a well-formed name lazily provisions its store; anything else returns 404 (`MEMORY_STORE_NOT_FOUND`).
- **FR-017a**: Surfaces MUST present a per-project store by a **human-readable identity derived from its `project_root`** — the root directory's basename as the primary label and the absolute root path as a secondary detail — never only the opaque `project-<ULID>` store name (the project ULID is a one-way digest of the root and is not human-recognisable). When the root is unknown (a store provisioned before the root was tracked) the surface falls back to the store name; the global store needs no derivation (its name `global` is already readable). The underlying store name stays `project-<ULID>` (FR-017) — this is a **display** concern. Verified by frontend tests; desktop acceptance is deferred to e2e like the other desktop-view items.
- **FR-017c**: A user MUST be able to set a **display label** for any memory store — a chosen name that takes precedence over the FR-017a `project_root` derivation in every surface. This gives a readable identity to a store whose originating folder was never recorded (where FR-017a would otherwise fall back to the opaque `project-<ULID>` name). Setting an empty / whitespace label clears it, reverting to the FR-017a derivation or fallback. The label is **display metadata**: it does not change the store name (FR-017) or `project_id`, and is set via `PATCH /memory_stores/{name}/label`. Verified by an HTTP acceptance test; the desktop rename view is deferred to e2e like the other desktop-view items.
- **FR-021**: The read-only fact viewer MUST offer, for both a fact file and its containing folder, affordances to (a) **open in external editor** and (b) **reveal in file manager / Finder**. Both perform the real OS action on **both** surfaces: the desktop (Tauri) build via the OS opener, the web build via the loopback daemon's filesystem-action endpoints (spec 004 FR-039), since the daemon is on the user's own machine (ADR-033). There is no copy-path fallback. Which editor opens is decided by the global preferred-editor preference (specced in 002-ui-shell; not re-specified here). The read responses MUST surface the absolute paths these affordances act on (see FR-022).
- **FR-022**: Read responses MUST surface the on-disk truth: the fact read endpoints (`GET …/facts`, `GET …/facts/{id}`) MUST include each fact file's absolute `.md` path and its containing folder's absolute path, and the store read endpoint (`GET …/{name}`) MUST include the store's absolute on-disk directory. These power the FR-021 open/reveal affordances and let a human locate the canonical file to correct out-of-band.

**Substrate isolation**

- **FR-018**: The retrieval/index engine (FTS5, sqlite-vec, embedding providers, converters) MUST be confined to infrastructure. Domain and application layers MUST NOT import index/engine types directly; interaction is via the shared retrieval port. mem0, chroma, and LlamaIndex MUST NOT be imported anywhere.

**Migration**

- **FR-019**: This branch is unreleased; there is **no new schema migration** for the lane layout (the `documents`/`chunks` schema is unchanged — only the on-disk lane location changes). A single migration MUST drop `memory_records` and create the fresh unified schema. Legacy on-disk engine directories (chroma/LlamaIndex) from pre-release builds are abandoned in place — nothing reads them — rather than deleted; old mem0/chroma text is not migrated. Legacy per-item files at a store root from pre-lane builds are likewise **abandoned in place** (not read, not deleted): the lazy reindex-on-read reconciles the `knowledge/` lane, so stale index rows for old root facts are reconciled away on the next `recall` until those items are re-remembered or seeded by the organizer. Existing `MEMORY.md` files on disk are left in place, unread.

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
- The canonical format is per-item markdown files (YAML frontmatter + body) under a per-scope `knowledge/` lane; there is no derived `MEMORY.md` index.
- The coffer-mcp-shim propagates its launch cwd to the daemon at session handshake on the supported agents (to verify in implementation).
- The knowledge base (spec 006) and memory share one unified substrate (`documents` table discriminated by `kind` + JSON `metadata`); they are two faces, not duplicated code.
- Single-user concurrency is small.
