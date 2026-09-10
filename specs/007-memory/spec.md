# Feature Specification: Knowledge Layer

> 中文版: [spec.zh.md](./spec.zh.md)

**Feature Branch**: `feature/kb-memory-redesign`
**Created**: 2026-05-22 (as *Memory*) · **Merged with spec 006 (Knowledge Base)**: 2026-09-10
**Status**: Accepted — shipped
**Folder name**: this spec lives at `specs/007-memory/`, which is **historical**. The directory name is the spec id used by every inbound link and by `scripts/audit_acceptance.py` (which keys acceptance markers on it), so it was deliberately left alone when the feature was renamed. Read `007-memory` as "the Knowledge Layer spec".

**Input**: Coffer stores one thing — **knowledge** — and serves it to every agent the user runs. Knowledge arrives two ways: an agent **writes** it (a fact, a decision, a preference worth surviving the session) or a human **ingests** it (a file in any format, converted to Markdown). It is held as per-item Markdown files on disk, the **sole source of truth**; SQLite (`documents`, `chunks`, FTS5, sqlite-vec) is a derived, rebuildable index ([ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md)). One resource kind, `knowledge`, with three scopes (`global`, `project-<ULID>`, and named collections), a fixed set of lanes per scope, one retrieval engine whose mode is internal ([ADR-034](../../docs/decisions/ADR-034-retrieval-mode-is-internal.md)), and eight `coffer__*` MCP tools. Coffer keeps its own canonical format and never writes into an agent's native memory files ([ADR-026](../../docs/decisions/ADR-026-memory-via-mcp-not-native-projection.md)); knowledge reaches a session only when the agent **asks for it** over MCP — nothing is pushed in.

## Why this is one layer (the 2026-09-10 merge)

This spec used to be one of two. Spec 006 owned a `knowledge_base` kind (upload files → Markdown → search) and spec 007 owned a `memory` kind (agents remember facts → recall). They were described as **two faces of one substrate**, and that was literally true in the code: `documents`, `chunks`, the FTS5 index and the sqlite-vec index were shared from the start (006 FR-009), and `infrastructure/knowledge/paths.py` already owned both on-disk layouts. The split existed only in the facade.

It was not earning its keep:

- **The knowledge base was an empty shell.** It was created 2026-06-22 and still held zero documents two and a half months later. Every one of the 78 rows in `documents` was `kind='memory'`. Its embedding config was never set.
- **Memory already had a `knowledge/` lane.** The `organize` pass existed precisely to turn raw notes into topic documents under it. Knowledge was already first-class *inside* memory.
- **The tool surface made callers guess.** An agent had to decide "is this memory or is this knowledge?" before it could choose between `coffer__recall` and `coffer__search_knowledge` — a distinction that means nothing to the caller and that the substrate did not honour anyway.
- **The retrieval tools' error rate was the symptom.** `coffer__grep_knowledge` failed 9 invocations out of 12 (ripgrep pointed at a directory that did not exist), `coffer__read_document` 3 of 3, and `coffer__search_knowledge` 3 of 12 — while `coffer__list_knowledge_bases` succeeded 4 of 4. Searching an empty knowledge base fails; listing it does not.

So the two kinds became one kind, the twelve tools became eight, and the two REST/CLI/UI surfaces became one each. What survives from 006 is everything that was actually about *ingesting files*: any-format conversion, chunking, source tracking, reindexing. What survives from 007 is everything that was about *agents writing and continuing work*: entries, the organizer, rules, handoff, scope merge.

**Existing data was cleared** by migration `0051`, and the reason is worth stating plainly rather than burying. `memory:global` and `knowledge_base:global` both existed, and `resources` is keyed by `(kind, name)` — converting both would collide, and any automatic rename would have been a guess about which one the user meant. Every `documents` row was a memory-side index over the **journal lane**, which the preceding change removed along with transcript distillation; the index pointed at files that no longer exist. Re-accumulation happens by explicit `coffer__write` and by file ingestion, which is exactly what files-as-truth already assumes: the index is derived, never the system of record.

## User Scenarios & Testing

### User Story 1 — One knowledge layer, every agent (Priority: P1)

The developer works on a project with Claude Code in the morning and Codex in the afternoon. While using Claude Code the agent learns "this repo deploys via `make release`, never `git push --tags` directly" and records it with `coffer__write`. In the afternoon, Codex — a different agent — finds the same fact with `coffer__search`, because both agents read and write **one shared scope**. No copy diverges.

**Why this priority**: This is the core. A per-agent silo that drifts across agents is the problem being solved; without a single shared source of truth there is no feature.

**Independent Test**: From a fresh install, run an MCP client in a git project, call `coffer__write` with a project fact, then from a second MCP client (different agent identity) in the same project call `coffer__search` and observe the fact returned. Confirm the fact exists as a per-item Markdown file under the project scope's `knowledge/inbox/` lane.

**Covering scenarios**:

- agent remembers a project fact
- agent recalls a project fact
- recall spans project and global scope
- remembered items are stored in the knowledge lane
- built-in memory tools appear in client tool list
- vector recall falls back when embedding is unconfigured

---

### User Story 2 — Three scopes: global, project, and named collections (Priority: P1)

Some knowledge is about the developer everywhere ("prefers tabs over spaces"); some is about one repo ("this service's API base path is `/api/v2`"); and some belongs in a collection the developer made on purpose ("`design-notes`", holding the PDFs and ADRs of a design review). All three are the same kind of thing with the same lanes and the same retrieval — only the **name** says which is which.

`global` and `project-<ULID>` **auto-provision** on first use, because an agent that wants to write something should not have to ask permission first. A named collection **does not**: it exists because someone decided it should, and silently conjuring one from a typo would be worse than an error.

**Why this priority**: Mixing personal preferences with project facts pollutes retrieval and leaks repo details across projects; forcing a deliberate corpus to live inside "memory" made it invisible. The scope axis is what makes the shared layer trustworthy.

**Independent Test**: Write one item with `scope=global` and one with no scope inside a git project. From a different project, search returns only the global item; from the original project, search returns both. Create a named collection `design-notes` explicitly and ingest a file into it; then search a name that does not exist and observe an error rather than a new empty scope.

**Covering scenarios**:

- remember at global scope
- agent remembers a project fact
- project scope resolves from the agent's working directory
- recall spans project and global scope
- create a knowledge base
- project memory follows the repository across checkout paths

---

### User Story 3 — Build a scope from arbitrary files (Priority: P1)

A developer has design notes, ADRs, internal wikis, PDFs of papers, a spreadsheet, and some HTML pages. They drop them all into a scope regardless of format. Coffer converts each to clean Markdown under the scope's `inbox/` lane, keeps the original in the hidden `.raw/` lane for provenance, and indexes the result so an agent can retrieve from it — through the same `coffer__search` that returns the agent's own written entries.

**Why this priority**: Ingestion is half of what the layer holds. Without it, the only knowledge Coffer has is what an agent happened to type.

**Independent Test**: Create a scope `design-notes`, ingest a `.md`, a `.pdf`, a `.docx`, and a `.csv`; observe each become a Markdown file under `~/.coffer/knowledge/design-notes/inbox/`, the original under `.raw/`, and a row in `documents` with `lane='inbox'`.

**Covering scenarios**: ingest converts any format to markdown; list documents in a knowledge base; filter documents by title; delete a single document; delete a knowledge base cleans up files and index; re-upload of an updated file updates the document in place; re-upload of an identical file is a no-op.

---

### User Story 4 — One retrieval surface over both lanes (Priority: P1)

The same scope is queried several ways under the hood: `grep` (exact/regex over the Markdown files, zero index), `keyword` (SQLite FTS5 + BM25 over a trigram tokenizer, so CJK and identifiers match), `vector` (sqlite-vec against a configured embedding provider), and `hybrid` (reciprocal rank fusion of keyword + vector). These are an **internal engine detail** ([ADR-034](../../docs/decisions/ADR-034-retrieval-mode-is-internal.md)): no external caller chooses a mode — a search resolves the scope's default strategy automatically (`hybrid` when vector is enabled, else `keyword`). Vector or hybrid without a configured embedding provider falls back to keyword internally — never blocked, never flagged per query (degradation is reported once, via `documents_degraded`).

Crucially, **retrieval spans both lanes**. A search over a scope returns the entries an agent wrote *and* the documents a human ingested, ranked together. Unified search is the point of merging the two kinds; a per-lane search would have re-created the split one level down.

**Why this priority**: Retrieval is the product. The internal modes cover offline/zero-config use through to semantic search, while the external surface stays "one query → one answer".

**Independent Test**: With a scope holding both a written entry and an ingested document, run one `coffer__search` and observe hits from both lanes. Run a grep query with no embedding config. Configure an embedding provider, enable `vector` on the scope, search again; remove the config and search again, observing results still return with no error.

**Covering scenarios**: keyword search returns ranked passages; keyword search matches CJK (Chinese) content; grep returns file/line matches; vector search returns ranked passages; vector falls back to keyword when embedding unconfigured; hybrid search fuses keyword and vector via RRF; a topic document recalls at passage granularity.

---

### User Story 5 — Agent reads AND writes through the MCP gateway (Priority: P1)

The developer's coding agent connects to Coffer's MCP endpoint and gets **eight** built-in tools: `coffer__search`, `coffer__grep`, `coffer__read`, `coffer__list`, `coffer__write`, `coffer__delete`, `coffer__set_handoff`, `coffer__resume`. Every one of the first six takes an optional `scope`, defaulting to the cwd's project scope and falling back to `global` outside a project. `coffer__write` files an entry from `text`, stores a Markdown document when given a `filename`, and rewrites either in place when given an `id` — the caller never has to know which lane a thing lives in. Every agent write is audited (F01) with the agent as actor and funnels through the same service paths the REST surface uses.

**Why this priority**: Agent-side retrieval is what makes the layer useful during coding; agent-side writing makes it a living store rather than a static vault. Eight tools that read as verbs are what removed the "is this memory or knowledge?" guess.

**Independent Test**: With a populated scope, an MCP client sees exactly the eight tools; calling `coffer__write` with `text` creates a searchable entry, calling it with `filename` creates a searchable document, and `coffer__read` returns either by id.

**Covering scenarios**: built-in KB tools appear in client tool list; built-in memory tools appear in client tool list; agent searches a knowledge base; agent greps a knowledge base; agent reads a document; agent adds a document via MCP; agent edits a document via MCP; agent deletes a document via MCP.

---

### User Story 6 — The user curates what accumulated (Priority: P2)

The developer wants to see and correct what has piled up: browse a scope's lanes in a **read-only** viewer, fix a drifted entry or a conversion artefact **in their own external editor** (or via the API/CLI), add an item by hand, delete a wrong one. Coffer's UI never edits content in-app; instead each file and its containing folder offer "open in external editor" and "reveal in file manager", performed by the local daemon ([ADR-033](../../docs/decisions/ADR-033-daemon-proxies-os-file-actions.md)). Any out-of-band correction is picked up by lazy reindex-on-read (FR-010). Once a document has been hand-edited (`source_mode = edited`), re-conversion from its original is blocked so an edit is never clobbered.

**Why this priority**: A knowledge layer without human curation is uncomfortable — agents sometimes record wrong things and converters sometimes mangle a table. Routing edits through the user's own editor keeps the Markdown files the sole source of truth with no second editing surface to keep in sync.

**Independent Test**: After agents have written entries and files have been ingested, open the Knowledge page (read-only) and confirm content renders but is not editable in-app. Correct one file outside Coffer and observe the next search return the corrected version. Add an item via the CLI/API, delete another, and observe it gone from disk and from search.

**Covering scenarios**: user adds a fact; user corrects a fact out-of-band; user deletes a fact; read-only viewer offers open/reveal affordances; edit a document and reindex; external edit picked up by reindex-on-read; re-conversion blocked once edited; changing chunk params re-indexes; changing embedding model re-embeds; check sources detects changed, unchanged, and missing originals; update from source refreshes a changed document in place; update from source refuses an edited document; auto_update_sources refreshes changed sources on check.

---

### User Story 7 — Inspect, name, reset, and consolidate scopes (Priority: P3)

The developer wants to know how much has accumulated per scope, to give a scope a readable name when its originating folder is unknown, to clear a scope without deleting it, and — when the same repository ended up with two project scopes — to merge them without losing anything.

**Why this priority**: Hygiene; not blocking the core flow.

**Independent Test**: View per-scope metrics (entry count, document count, chunk count, disk bytes). Rename a scope whose folder is unknown and confirm the chosen name shows in the list and survives a reload. Clear a project scope; confirm every entry is gone but the scope remains. Run a merge scan across project scopes and merge a proposed pair.

**Covering scenarios**: clear a memory scope; user renames a memory store; KB metrics report counts and disk usage; degraded embed surfaces documents_degraded and retries without re-chunking; test an embedding model; merge scan proposes same-project stores; merge scan degrades cleanly without an internal engine; merging two stores consolidates additively and retires the source; a merged identity resolves to the surviving store.

---

### User Story 8 — Continue the same work across agents and machines (Priority: P2)

The developer pauses mid-task with Claude Code — at a known step, with specific next steps and files in flight — and later resumes from a different agent (Codex) or a second machine. Before pausing the agent calls `coffer__set_handoff` with the current working state ("现场"): what it was doing, what's next, which files are open, and any unresolved questions. Coffer keys that scene by **(project × git branch)** and writes it into the project scope's `handoff/` lane. When work resumes, `coffer__resume` returns the saved scene for the current branch (annotated with how stale it may be) — or reports that none exists for a fresh branch.

**Why this priority**: Continuity is the north star, but it builds on the shared core (Stories 1–2): a handoff is an additive working lane, not a prerequisite for search. Branch-keying means parallel branches and worktrees keep independent scenes and never clobber each other; there is no global handoff (a global "current task" is meaningless), so a cwd outside any git project has nothing to resume.

**Independent Test**: From an MCP client inside a git project on branch `work`, call `coffer__set_handoff` with a body, then from a second client (different agent identity) in the same project + branch call `coffer__resume` and observe the same body with the branch and a freshness annotation. On a fresh branch, `coffer__resume` reports `found=false`.

**Covering scenarios**: agent saves and resumes a working-state handoff; resume reports no handoff for a fresh branch.

---

### User Story 9 — Rules accumulate in a lane of their own (Priority: P2)

The developer has accumulated behavioural rules (global "always run the verify step before pushing", project "this repo deploys via `make release`") and wants them kept as rules — a readable list of standing instructions — rather than dissolved into topic prose. The organizer recognises a rule-shaped note and **appends** it to the scope's `rules/` lane instead of merging it into a topic document. The lane sits at the scope root, outside retrieval, and is read **on demand** through its own surface: `GET /api/v1/knowledge/{scope}/rules` or `coffer knowledge rules <scope>`. Coffer never writes into the agent's own memory or instruction files ([ADR-026](../../docs/decisions/ADR-026-memory-via-mcp-not-native-projection.md)).

**Why this priority**: procedural knowledge has a different shape from topical knowledge — a rule is a standing instruction, not a search hit — so it earns a lane that retrieval leaves alone. It is P2 because it builds on the organizer and the shared core: the lane stores rules that the ordinary write path already produced.

**What this story no longer covers — and the cost.** Rules used to arrive **ambiently**. Coffer installed a `coffer-hook` SessionStart hook into each managed agent; on every session start (and resume/clear/compact) the hook called `GET /api/v1/agents/{name}/session-context?cwd=<cwd>` and injected the scope's rules, two Coffer-seeded built-in rules, and a title-only index of the project's knowledge as `additionalContext`. That entire delivery channel is **removed** — FR-049, FR-050, FR-052 and FR-055 are deleted, along with the `coffer-hook` binary, the hook install/uninstall surface, the `session-context` route and the bundle assembler. Nothing pushes anything into an agent session any more. See "Delivery — removed" under Functional Requirements for the full statement of what that costs.

**Independent Test**: Write a rule-shaped note through the ordinary write path, run `organize`, and confirm it lands appended in `rules/rules.md` rather than merged into a topic document, with `rules_appended` counted in the result. Then read it back with `coffer knowledge rules <scope>` and over `GET /api/v1/knowledge/{scope}/rules`, and confirm a scope with no rules returns empty rather than an error.

**Covering scenarios**: the organizer routes a rule-shaped note into the rules lane; the rules read surface returns the stored rules.

---

### User Story 10 — Read the whole scope, lane by lane (Priority: P2)

The developer opens a scope in Coffer and wants to see **everything it holds**, not one flat list: the **Entries** an agent wrote, the **Documents** someone ingested, the procedural **Rules**, the per-branch **Handoff** scenes, and the organizer's **Changelog**. The Knowledge detail page presents exactly those five tabs. Each gets a shape-fit view: Entries and Documents are trees plus content, Rules is a single document, Handoff is a per-branch list, Changelog is an append-only log. Every view is **read-only**, renders through the unified file preview, and offers open-in-editor / reveal / copy-path on the underlying file.

Entries and Documents are separate tabs with separate counts precisely because they have different provenance and different curation gestures — but the tabs are a *presentation* split, not a storage or retrieval one. `coffer__search` still crosses them.

**Why this priority**: a flat list hides most of what a scope holds — rules live outside retrieval and handoff scenes are working state — so the procedural and continuity knowledge would be invisible even though it is all on disk. It is P2 because it is a read-only projection over lanes the other stories already populate; it adds visibility, never a new write path.

**Independent Test**: Populate a project scope with an entry, an ingested document, a rule, a handoff scene, and an organizer run that writes a changelog. Open the detail page and confirm five tabs, each read-only, each rendered via the unified file preview, each offering open / reveal / copy-path.

**Covering scenarios**: handoff scenes are listed per branch for a store; the consolidation changelog is readable for a store; the organizer drains the inbox into a topic document; organizing merges a note into an existing topic without clobbering it; organize is a no-op when no internal model is configured; the reorg pass consolidates duplicate topic documents; reorg never destroys content — a superseded topic stays recoverable; reorg is a no-op when no internal model is configured; memory is auto-organized after the store goes idle.

---

### Edge Cases

- **A scope name that does not exist**: `global` and a well-formed `project-<26-char ULID>` lazily provision. Any other name is a **named collection** and is NOT auto-provisioned — an unknown one is a 404, so a typo cannot silently create an empty scope that then fails every read.
- **Vector unavailable, embedding unconfigured**: search falls back to keyword internally and returns results; it never blocks and never sets a query-time flag. The default (`keyword` + `grep`) is zero-config and offline.
- **Unsupported format**: a file with no converter is rejected with `IngestRejected("unsupported_type")`; nothing is persisted.
- **Converter library missing**: if the converter engine for a format is not installed, ingest of that format returns `EngineUnavailable` naming the missing dependency; the daemon stays up and other formats still ingest.
- **Empty conversion**: a file converting to empty/whitespace-only Markdown is rejected with `IngestRejected("empty")`. A **PDF** that converts empty is rejected as `IngestRejected("scanned_pdf")` (same 415) so the UI can say "looks scanned/image-only — run OCR" instead of something generic.
- **Oversized file**: a file over `max_document_bytes` (default 25 MB) is rejected at the API boundary before any conversion runs.
- **Re-upload, identical bytes**: an idempotent no-op — the existing document is returned, nothing re-written or re-audited.
- **Re-upload, changed bytes, same filename**: updates the **same document in place** (ULID reused, `inbox/` + `.raw/` overwritten keeping only the latest original, `source_mode` reset to `converted`) — but only with `replace=true`; without it the upload is rejected (`duplicate`) so the overwrite is always explicit.
- **Re-conversion after edit**: re-converting a document whose `source_mode == edited` is rejected; re-uploading a changed source with `replace=true` updates it in place and resets it to `converted`.
- **Direct disk edit**: the next read lazily scans for deltas by content hash and reindexes, so out-of-band edits are picked up with no watcher. Reindexing unchanged content is a no-op.
- **Empty or over-long entry text**: rejected at the API boundary (`max_entry_chars`, default 8192, hard ceiling 32768); nothing written.
- **Resume on a fresh branch**: `coffer__resume` returns `found=false` rather than erroring; nothing is fabricated.
- **Handoff outside a git project**: no project scope and no branch, so `coffer__resume` returns `found=false` and `coffer__set_handoff` is rejected (there is no global handoff).
- **An agent that never asks for the rules**: nothing happens. With the session-start delivery channel removed, an agent that does not call `coffer__recall` / `coffer__search` (or read `GET /api/v1/knowledge/{scope}/rules`) simply never sees the lane. This is the accepted consequence, not a bug — see "Delivery — removed".
- **Grep and the ingested originals**: `.raw/` is dot-prefixed so ripgrep skips it. Without that, every ingested document produced two grep hits — the Markdown and the original it was converted from.
- **Tracked source moved/deleted**: `check-sources` reports it `missing` and never crashes. `source_path` is machine-local, so a `missing` result on another machine is expected and benign.
- **Concurrent searches**: multiple searches against one scope run independently; no per-scope lock degrades read latency.

## Acceptance Scenarios

Every scenario maps to at least one test marked `@pytest.mark.acceptance(spec="007-memory", scenario="…")` (Python) or `acceptance("007-memory", "…")` (TypeScript). Some headings keep the vocabulary of the pre-merge specs — "fact", "memory store", "knowledge base" — because the heading text *is* the marker key that `scripts/audit_acceptance.py` matches. They read as historical labels; the bodies describe today's behaviour.

### Scenario: project memory follows the repository across checkout paths

- **Given** the same repository (same `origin` remote) checked out at different
  paths — e.g. on two synced machines with different usernames
- **When** each checkout resolves its per-project knowledge scope
- **Then** both resolve to the same scope (same project ULID)
- **And** a scope provisioned under the legacy path-derived id is adopted under
  the portable id on first resolve, keeping its entries, root mapping, and label

### Scenario: agent remembers a project fact

- **Given** an MCP client running inside a git project,
- **When** it calls `coffer__write` with `text` and no `scope`,
- **Then** a per-item Markdown file (YAML frontmatter `title`/`description`/`metadata.actor`/`origin_session_id` + body) is written under the project scope's `knowledge/inbox/` lane, the file is indexed into `documents` with `lane='knowledge'`, and an audit entry is recorded.

### Scenario: agent recalls a project fact

- **Given** a project scope with entries,
- **When** an MCP client calls `coffer__search` with a query,
- **Then** ranked hits are returned with id, text, score, source, and time, after a lazy reindex scan picks up any out-of-band deltas.

### Scenario: recall spans project and global scope

- **Given** knowledge exists at both global and project scope,
- **When** an MCP client calls `coffer__search` without a scope,
- **Then** results are drawn from both the project scope and the global scope.

### Scenario: remembered items are stored in the knowledge lane

- **Given** an MCP client running inside a git project,
- **When** it calls `coffer__write` with `text`,
- **Then** the item is written as a Markdown file under the project scope's `knowledge/inbox/` lane (never at the scope root), it is indexed into `documents` under the `knowledge` lane, and a subsequent `coffer__search` returns it.

### Scenario: remember at global scope

- **Given** an MCP client,
- **When** it calls `coffer__write` with `scope=global`,
- **Then** the entry is written to the `global` scope, keyed by `project_id = WORKSPACE_GLOBAL_PROJECT_ID`, and a search from any project returns it.

### Scenario: project scope resolves from the agent's working directory

- **Given** the coffer-mcp-shim reports its launch cwd at session handshake,
- **When** the daemon resolves the project knowledge scope,
- **Then** it computes the git-root of that cwd and resolves — lazily provisioning if absent — the `project-<ULID>` scope for that project.

### Scenario: out-of-band fact-file edits are visible on recall

- **Given** a project scope with entries,
- **When** an entry file is edited out-of-band directly on disk (frontmatter preserved),
- **Then** the next `coffer__search` returns the edited content (lazy reindex-on-read), with no filesystem watcher running.

### Scenario: user adds a fact

- **Given** a knowledge scope,
- **When** the user adds an entry via the Coffer UI or CLI,
- **Then** the canonical Markdown is written under the scope's `knowledge/inbox/` lane with `metadata.actor = "user"`, the row is indexed under the `knowledge` lane, and an audit entry is recorded.

### Scenario: user corrects a fact out-of-band

- **Given** an entry exists,
- **When** the user corrects its text outside the in-app viewer — via the REST/CLI write surface (`PATCH /api/v1/knowledge/{scope}/entries/{id}` / `coffer knowledge edit-entry`) or by editing the canonical Markdown directly in an external editor,
- **Then** the canonical Markdown is rewritten, the row is reindexed (immediately for the REST/CLI path; on the next read via lazy reindex-on-read for a direct file edit), and search reflects the new text.

### Scenario: user deletes a fact

- **Given** an entry exists,
- **When** the user deletes it,
- **Then** the Markdown file and its index rows are removed, and search no longer returns it.

### Scenario: read-only viewer offers open/reveal affordances

- **Given** an item viewed on the Knowledge page,
- **When** the user inspects it (and its containing folder),
- **Then** the content renders read-only (no in-app content editing), the read responses surface the item's absolute on-disk `.md` path and its containing folder's absolute path, and the UI offers "open in external editor" + "reveal in file manager" for both file and folder via the loopback daemon (spec 004 FR-039) — with no copy-path fallback; which editor opens is decided by the global preferred-editor preference (see 002-ui-shell).

### Scenario: clear a memory scope

- **Given** a knowledge scope with entries,
- **When** the user clears it,
- **Then** every item under the `knowledge/` lane is removed and its index rows dropped, but the scope Resource is preserved.

### Scenario: user renames a memory store

- **Given** a knowledge scope (e.g. one whose originating folder was never recorded, so it would otherwise show as `project-<ULID>`),
- **When** the user sets a display label via `PATCH /api/v1/knowledge/{scope}/label`,
- **Then** the label is trimmed, echoed back, surfaced on the scope read + list as the readable name, and an empty / whitespace label clears it (reverting to the FR-017a derivation); labelling an unknown scope is a 404, not an autocreate.

### Scenario: built-in memory tools appear in client tool list

- **Given** an MCP client connects to Coffer's gateway,
- **When** the client lists tools,
- **Then** `coffer__search`, `coffer__write`, `coffer__list`, `coffer__set_handoff`, and `coffer__resume` appear alongside other built-in and upstream tools.

### Scenario: vector recall falls back when embedding is unconfigured

- **Given** a knowledge scope with no embedding provider configured installation-wide,
- **When** the engine resolves to a vector strategy but no embedder is available,
- **Then** the call runs a keyword search instead and returns results with no error; the degradation is NOT surfaced as a query-time response flag.

### Scenario: agent saves and resumes a working-state handoff

- **Given** an MCP client running inside a git project on a branch,
- **When** it calls `coffer__set_handoff` with a body and later (possibly as a different agent) calls `coffer__resume`,
- **Then** `set_handoff` writes a per-`(project × branch)` Markdown file (frontmatter `branch`/`updated_at` + freeform body) under the project scope's `handoff/` lane — overwriting any prior scene for that branch and recording a `handoff_set` audit entry — and `resume` returns `found=true` with the saved branch, body, `updated_at`, and a freshness `note`; the handoff is never returned by `coffer__search`.

### Scenario: resume reports no handoff for a fresh branch

- **Given** an MCP client in a git project on a branch with no saved handoff (or a cwd outside any git project),
- **When** it calls `coffer__resume`,
- **Then** the call returns `found=false` (never an error and nothing fabricated).

### Scenario: the organizer drains the inbox into a topic document

- **Given** a knowledge scope with two freshly-written entries in its
  `knowledge/inbox/` and an internal model configured,
- **When** `POST /api/v1/knowledge/{scope}/organize` (or `coffer knowledge
  organize <scope>`) is called,
- **Then** the internal LLM organizer drains the inbox (no items remain), at
  least one `knowledge/<topic>.md` topic document exists holding the merged
  content, `knowledge/INDEX.md` lists that topic, a `memory_organized` audit
  entry is recorded, and a subsequent search returns content from the topic
  document (not the now-empty inbox).

### Scenario: organizing merges a note into an existing topic without clobbering it

- **Given** a knowledge scope that already has a hand-edited topic document
  containing content X plus a new related item in its `knowledge/inbox/`,
- **When** `organize` is called and the organizer merges the new item into that
  topic,
- **Then** the topic document still contains the original content X alongside
  the newly integrated information, the inbox item has been removed, and the
  consolidation changelog (`consolidation-log.md`) records the merge — the
  organizer never regenerates from scratch and never clobbers a human edit.

### Scenario: organize is a no-op when no internal model is configured

- **Given** a knowledge scope with items in its `knowledge/inbox/` but no internal
  model configured,
- **When** `organize` is called,
- **Then** the call returns `status="no_model"`, the inbox is left untouched, no
  topic document is written, and no error is raised.

### Scenario: a topic document recalls at passage granularity

- **Given** an organized knowledge scope whose `knowledge/` lane holds a topic
  document with two distinct heading sections, each describing a different
  subject, indexed for retrieval,
- **When** `coffer__search` is queried with terms that occur only in the second
  section,
- **Then** the returned hit's text is that section's **passage** — not the whole
  document — so the first section's distinctive wording does not appear in the
  hit, confirming topic documents are chunked **per passage** (heading- and
  block-structure aware) rather than one chunk per file.

### Scenario: the reorg pass consolidates duplicate topic documents

- **Given** a knowledge scope with two overlapping topic documents (both about the
  same subject, one carrying extra detail) and an internal model configured,
- **When** `POST /api/v1/knowledge/{scope}/reorg` (or `coffer knowledge reorg <scope>`)
  runs and the internal agentic loop reads both documents, writes the merged
  content into one, and supersedes the now-redundant other,
- **Then** a single topic document holds the combined content, the redundant
  document no longer appears in search or `INDEX.md`, a subsequent search
  returns the merged content, and a `memory_reorganized` audit entry is recorded.

### Scenario: reorg never destroys content — a superseded topic stays recoverable

- **Given** a knowledge scope with a topic document holding content X (possibly a
  human edit),
- **When** the reorg loop overwrites or supersedes that document,
- **Then** the prior content X is first archived to the scope's `superseded/`
  tombstone (so it is **recoverable**, never hard-deleted), the tombstone is
  **excluded from retrieval** (it lives outside the `knowledge/` lane), and the
  consolidation changelog records the supersession — the loop is an incremental
  edit, never a from-scratch regeneration.

### Scenario: reorg is a no-op when no internal model is configured

- **Given** a knowledge scope with topic documents but no internal model configured,
- **When** `reorg` is called,
- **Then** the call returns `status="no_model"`, no topic document is written,
  superseded, or archived, and no error is raised.

### Scenario: memory is auto-organized after the store goes idle

- **Given** the auto-organize trigger is enabled, an internal model is
  configured, and an item is freshly written into a scope's `knowledge/inbox/`,
- **When** the scope goes idle (no further knowledge writes) for the conservative
  debounce delay,
- **Then** the organizer runs **automatically in the background** — with no
  explicit `organize` call — draining the inbox into a topic document, and the
  background pass never blocks: cancelling the pending trigger (e.g. at daemon
  shutdown) before it fires simply leaves the inbox intact for a later pass.

### Scenario: the organizer routes a rule-shaped note into the rules lane

- **Given** a knowledge scope with an internal model configured and two freshly
  written inbox items — one a behavioural rule ("always run the verify step
  before pushing") and one an ordinary fact,
- **When** `organize` runs and the organizer classifies the first item as a rule
  and the second as ordinary knowledge,
- **Then** the rule is appended to the scope's procedural `rules/rules.md` lane
  (not written into a `knowledge/<topic>.md` doc), the ordinary fact becomes a
  topic document, both inbox items are drained, and search does NOT surface the
  rule (the `rules/` lane sits outside the retrieval glob, like `handoff/` and
  `superseded/`).

### Scenario: the rules read surface returns the stored rules

- **Given** a knowledge scope whose `rules/rules.md` holds one or more rules,
- **When** `GET /api/v1/knowledge/{scope}/rules` (or `coffer knowledge rules <scope>`)
  is called,
- **Then** the response returns the rules text verbatim (the only surface the
  lane leaves disk through), and a scope with no rules returns an
  empty/`null` body rather than an error.

### Scenario: handoff scenes are listed per branch for a store

- **Given** a knowledge scope whose `handoff/` lane holds one or more per-branch
  scene files,
- **When** `GET /api/v1/knowledge/{scope}/handoff` is called (addressed by
  scope name, not cwd),
- **Then** the response lists one scene **per branch**, each carrying its
  `branch`, `text`, `updated_at`, absolute on-disk `path`, and `folder_path`; a
  scope with no handoff scenes returns an **empty list with HTTP 200** (never a
  404).

### Scenario: the consolidation changelog is readable for a store

- **Given** a knowledge scope whose organizer has written a `consolidation-log.md`
  at the scope root,
- **When** `GET /api/v1/knowledge/{scope}/consolidation-log` is called
  (addressed by scope name, not cwd),
- **Then** the response returns the changelog `text` with its absolute on-disk
  `path` and `folder_path`; a scope with no changelog returns `text = null` with
  HTTP 200 (never a 404).

### Scenario: merge scan proposes same-project stores

- **Given** two per-project scopes that describe the same project — one pair
  provably (both roots locally readable and normalizing to the same origin
  remote) and one pair only plausibly (labels/paths/content align but no
  common remote is provable),
- **When** the user runs the merge scan with an internal engine configured,
- **Then** the provable pair is proposed with `confidence="certain"` and
  `judged_by="remote"` without consulting the engine, the plausible pair is
  proposed with the engine's verdict (`judged_by="engine"`, a confidence and
  a reason), and each proposal suggests the surviving scope per the direction
  heuristic — and nothing is mutated by the scan.

### Scenario: merge scan degrades cleanly without an internal engine

- **Given** per-project scopes including a provably-same pair, and no
  internal engine configured,
- **When** the user runs the merge scan,
- **Then** the response reports `engine="no_model"` and still carries the
  deterministic (`judged_by="remote"`) proposals; engine-tier pairs are
  simply absent — no error.

### Scenario: merging two stores consolidates additively and retires the source

- **Given** two per-project scopes each holding entries (with at least one
  colliding lane filename),
- **When** the user merges the source into the target,
- **Then** every source lane file lands under the target (the filename
  collision keeping both copies), the source's label and root mapping move to a
  target that lacked its own, the target's retrieval returns the merged
  entries, the source scope (resource, index rows, on-disk dir) is retired, and
  a `memory_stores_merged` audit entry is recorded.

### Scenario: a merged identity resolves to the surviving store

- **Given** scope `project-X` was merged into `project-Y` (so `X` is listed
  in `Y`'s `merged_identities`),
- **When** an agent writes an entry from a checkout whose computed project
  identity is `X`,
- **Then** the entry is written to `project-Y` and no new `project-X` scope is
  provisioned.

### Scenario: create a knowledge base

- **Given** the daemon is running and no named collections exist,
- **When** the user creates a scope with a unique name and a retrieval config,
- **Then** the scope is persisted as a `knowledge` resource, `~/.coffer/knowledge/<name>/` is created with its lanes, and listing scopes shows it. A named collection is created **explicitly** — unlike `global` and `project-<ULID>`, it never auto-provisions from a read.

### Scenario: ingest converts any format to markdown

- **Given** a knowledge scope exists,
- **When** the user uploads a non-Markdown file (e.g. `.pdf`, `.docx`, `.csv`, `.html`),
- **Then** Coffer converts it to Markdown at `inbox/<doc-id>.md` (with YAML frontmatter), preserves the original at `.raw/<doc-id>.<ext>`, inserts a `documents` row (`kind="knowledge"`, `lane="inbox"`, `source_mode="converted"`), chunks it into FTS5, and records audit `KB_DOCUMENT_INGESTED`.

### Scenario: list documents in a knowledge base

- **Given** documents have been ingested,
- **When** the user lists documents,
- **Then** they see one row per ingested document with stable doc ids, titles, original filenames, and timestamps, paginated — and **only** documents: the listing is lane-scoped, so the entries an agent wrote into the same scope are not mixed in.

### Scenario: filter documents by title

- **Given** a scope with multiple documents,
- **When** the user lists documents with a title query `q`,
- **Then** only documents whose title contains `q` (case-insensitive) are returned, `total` reflects the filtered count, and results stay paginated by `limit`/`offset`.

### Scenario: keyword search returns ranked passages

- **Given** documents are indexed,
- **When** the user searches (no mode; Coffer uses the scope's resolved default strategy),
- **Then** they receive passages ranked by `bm25()`, each carrying its source doc id, title, snippet, and score — drawn from **both** lanes, since a search over a scope covers what was written and what was ingested.

### Scenario: keyword search matches CJK (Chinese) content

- **Given** a knowledge scope with a document whose Markdown body is Chinese (no word-boundary spaces),
- **When** the user runs a keyword search with a CJK query,
- **Then** a multi-character query (e.g. `向量检索`) matches via the FTS5 trigram index, and a short `< 3`-character query (e.g. `向量`) matches via the substring fallback — neither returns empty as the old `unicode61` tokenizer did.

### Scenario: grep returns file/line matches

- **Given** documents are on disk,
- **When** the user greps the scope with a pattern,
- **Then** Coffer runs ripgrep over the scope directory (bounded by max-matches and a timeout) and returns `{path, line_number, line}` hits with no index involved. The hidden `.raw/` lane is skipped, so an ingested document yields one hit for its Markdown rather than two.

### Scenario: vector search returns ranked passages

- **Given** an embedding provider is configured installation-wide and the scope lists a vector retrieval mode with its documents embedded,
- **When** the engine runs a vector search (a vector-enabled scope's resolved default),
- **Then** Coffer embeds the query, runs a sqlite-vec KNN, and returns top-k passages with similarity scores.

### Scenario: vector falls back to keyword when embedding unconfigured

- **Given** no embedding provider is configured installation-wide,
- **When** the engine resolves to a vector strategy but no embedder is available,
- **Then** Coffer runs a keyword search instead and returns results with no error; the degradation is NOT surfaced as a query-time flag (it is reported via `documents_degraded`).

### Scenario: hybrid search fuses keyword and vector via RRF

- **Given** a scope with vector enabled and documents embedded,
- **When** the engine fuses keyword+vector for a vector-enabled scope (its resolved default),
- **Then** Coffer runs BOTH keyword and vector searches and fuses them by reciprocal rank fusion (`K = 60`, deduped by `(document_id, position)`), so a passage ranked by both lists outranks single-list hits, and returns the fused top-k.

### Scenario: edit a document and reindex

- **Given** a converted document exists,
- **When** the user replaces its Markdown body through the edit API,
- **Then** `source_mode` becomes `edited`, the single re-index routine deletes old chunks/FTS5/vec rows and re-chunks (re-embedding if vector is enabled), and subsequent search reflects the edit.

### Scenario: external edit picked up by reindex-on-read

- **Given** a document whose Markdown file is edited out-of-band in the user's external editor (no API call),
- **When** the user next reads or searches that document,
- **Then** the lazy reindex-on-read scan detects the drifted `content_sha256`, re-indexes through the single idempotent routine, and the read/search reflects the edit — with no filesystem watcher running.

### Scenario: re-conversion blocked once edited

- **Given** a document whose `source_mode == edited`,
- **When** the user requests re-conversion from the raw original,
- **Then** Coffer rejects it with a clear error; re-uploading a new source file resets `source_mode` to `converted`.

### Scenario: changing chunk params re-indexes

- **Given** a scope with indexed content,
- **When** the user changes `chunk_size` or `chunk_overlap`,
- **Then** Coffer re-chunks and re-indexes the scope (and re-embeds if vector is enabled) — chunk params are mutable, not locked.

### Scenario: changing embedding model re-embeds

- **Given** a scope with a vector retrieval mode listed and an embedding model set installation-wide,
- **When** the user changes the embedding model,
- **Then** Coffer re-embeds the corpus into sqlite-vec — the embedding model is mutable, not locked. The model lives in the installation-wide config, not on the scope, so one change re-embeds every scope that asked for vectors; the UI confirms before applying it.

### Scenario: delete a single document

- **Given** a scope has documents,
- **When** the user deletes one document by id,
- **Then** the `inbox/<doc-id>.md` and `.raw/<doc-id>.<ext>` files are removed, its chunks/FTS5/vec rows are deleted, the `documents` row is removed, audit `KB_DOCUMENT_DELETED` is recorded, and search no longer returns it.

### Scenario: delete a knowledge base cleans up files and index

- **Given** a scope has content and an index,
- **When** the user deletes the scope through the generic resource delete (`DELETE /api/v1/resources/knowledge/{name}`),
- **Then** all of its `documents`/`chunks`/FTS5/vec rows are removed, `~/.coffer/knowledge/<name>/` is removed, and the Resource row is deleted. There is deliberately **no** `DELETE /api/v1/knowledge/{scope}`: scope lifecycle is kind-agnostic and belongs to the Resource framework.

### Scenario: built-in KB tools appear in client tool list

- **Given** an MCP client connects to Coffer's gateway,
- **When** it lists tools,
- **Then** the eight knowledge tools are present — `coffer__search`, `coffer__grep`, `coffer__read`, `coffer__list`, `coffer__write`, `coffer__delete`, `coffer__set_handoff`, `coffer__resume` — with no separate document-vs-memory families, and each of the first six accepting an optional `scope`.

### Scenario: agent searches a knowledge base

- **Given** a scope with indexed content,
- **When** the client calls `coffer__search(query, scope?, top_k?)`,
- **Then** Coffer returns ranked passages structured for LLM consumption (passage + source id + score), spanning both lanes.

### Scenario: agent greps a knowledge base

- **Given** a scope with files on disk,
- **When** the client calls `coffer__grep(pattern, scope?)`,
- **Then** Coffer returns file/line matches.

### Scenario: agent reads a document

- **Given** an item exists in a scope,
- **When** the client calls `coffer__read(id, scope?)`,
- **Then** Coffer returns the item's Markdown body and frontmatter — resolving an entry id or a document id automatically — or a clear error if the id is unknown.

### Scenario: agent adds a document via MCP

- **Given** a knowledge scope exists,
- **When** the client calls `coffer__write(text, filename, scope?)` with Markdown content,
- **Then** Coffer ingests it like a human upload (a new ULID-id document under the `inbox` lane, `inbox/` + `.raw/` written, indexed), records audit `KB_DOCUMENT_INGESTED` with the agent as actor, and the document is searchable.

### Scenario: agent edits a document via MCP

- **Given** a converted document exists,
- **When** the client calls `coffer__write(text, id, scope?)` naming that document,
- **Then** the body is replaced, `source_mode` becomes `edited`, the scope is reindexed, and audit `KB_DOCUMENT_UPDATED` is recorded with the agent as actor.

### Scenario: agent deletes a document via MCP

- **Given** a document exists in a scope,
- **When** the client calls `coffer__delete(id, scope?)`,
- **Then** the document's files and index rows are removed, audit `KB_DOCUMENT_DELETED` is recorded with the agent as actor, and search no longer returns it.

### Scenario: re-upload of an updated file updates the document in place

- **Given** a document ingested from `report.md`,
- **When** the user re-uploads a changed `report.md` with `replace=true`,
- **Then** the SAME document id is updated in place (`.raw/` + Markdown overwritten, only the latest original kept, `source_mode` reset to `converted`), no second document is created, and audit `KB_DOCUMENT_UPDATED` is recorded.

### Scenario: re-upload of an identical file is a no-op

- **Given** a document ingested from `report.md`,
- **When** the user re-uploads the byte-identical `report.md`,
- **Then** it is an idempotent no-op: the existing document is returned, no second document is created, and no `KB_DOCUMENT_UPDATED` audit is recorded.

### Scenario: KB metrics report counts and disk usage

- **Given** a scope holds entries and documents,
- **When** the user opens its detail view (UI or `coffer knowledge describe`),
- **Then** they see a lane-scoped `entry_count` and `document_count`, the chunk count, the indexed retrieval modes, the count of documents with a pending vector embed (`documents_degraded`), and the on-disk byte size of `~/.coffer/knowledge/<scope>/`. The two counts are separate because the two lanes have different provenance; the chunk count spans both, because retrieval does.

### Scenario: degraded embed surfaces documents_degraded and retries without re-chunking

- **Given** a vector-enabled scope whose embedding provider is unavailable when a document is ingested,
- **When** the document is indexed keyword-only and the user later reads the scope (list / search / metrics) with the provider still down, then again once it is restored,
- **Then** the document carries its real `content_sha256` and a persisted `embed_pending` flag, `documents_degraded` reports `1` on the degraded read, and the next reconcile retries **only** the embed (no re-chunk / FTS rewrite — the chunk rows are unchanged), clearing `embed_pending` so `documents_degraded` returns to `0`.

### Scenario: check sources detects changed, unchanged, and missing originals

- **Given** documents ingested from external files (their absolute `source_path` recorded in metadata),
- **When** the user runs `check-sources` after one original is edited on disk, one is left untouched, and one is deleted,
- **Then** the report classifies them as `changed`, `unchanged`, and `missing` respectively (by re-hashing each external file against the stored `source_sha256`), and nothing is re-indexed or audited by the detection itself.

### Scenario: update from source refreshes a changed document in place

- **Given** a converted document whose external `source_path` original has changed on disk,
- **When** the user runs `update-source` for that document,
- **Then** Coffer re-ingests it from the tracked file in place (same ULID id, `source_mode` stays `converted`), the new content is searchable and the old content is gone, and `KB_DOCUMENT_UPDATED` is audited.

### Scenario: update from source refuses an edited document

- **Given** a document whose `source_mode == edited`,
- **When** the user runs `update-source` for it,
- **Then** Coffer refuses with the re-conversion-blocked error (hand edits are never clobbered), and `check-sources` reports that document as `edited` rather than overwriting it.

### Scenario: auto_update_sources refreshes changed sources on check

- **Given** a scope with `auto_update_sources` enabled and a document whose external original has changed,
- **When** the user runs `check-sources`,
- **Then** the changed document is auto-refreshed in place (reported `updated`) and `KB_DOCUMENT_UPDATED` is audited, while a hand-edited changed document would be skipped (reported `edited`).

### Scenario: test an embedding model

- **Given** an embedding provider, model id, and (where required) credential ref,
- **When** the user tests the embedding model,
- **Then** Coffer requests one embedding and reports success with the returned
  vector dimension, or a humanized failure message, without persisting anything.

> **Deferred to future test work** (tests land with the e2e infrastructure; `make verify-acceptance` does not gate on them): the Knowledge list view per scope, the read-only viewer's open-in-editor / reveal affordances end-to-end, `coffer knowledge …` end-to-end with a running daemon, and per-scope metrics through the HTTP route.

## Requirements

### Functional Requirements

> **Numbering.** `FR-001`–`FR-059` keep the numbers they had while this was the *Memory* spec — they are cited from code comments, other specs and ADRs, so renumbering them would break more than it tidied. The requirements folded in from spec 006 (Knowledge Base) are renumbered into a fresh block, `FR-060`–`FR-075`, each noting the 006 number it came from. Gaps in the sequence are requirements retired by earlier changes (notably transcript distillation and the `journal` lane).

**Storage & scope**

- **FR-001**: System MUST store every written item as a per-item Markdown file (YAML frontmatter `title`/`description`/`metadata.actor`/`origin_session_id` + body) under a scope's **`knowledge/` lane** — freshly-written items in `knowledge/inbox/`, organized topic documents at `knowledge/<topic>.md` plus an `INDEX.md` maintained by the consolidation organizer. The Markdown files are the **sole source of truth**; SQLite is a rebuildable index. No derived index file is generated for retrieval.
- **FR-002**: System MUST support **one resource kind `knowledge`** with **three scopes**, discriminated by the resource name and nothing else: `global`, `project-<ULID>`, and any other name (a **named collection**). `global` and `project-<ULID>` MUST auto-provision on first use; a named collection MUST NOT — an unknown name is a 404, so a typo cannot conjure an empty scope. The scope kind is *derived* from the name (`domain/knowledge/scope.scope_kind_of`), never stored, so the two can never disagree.
- **FR-002a**: System MUST store every scope under one root, `~/.coffer/knowledge/<scope>/`, with a fixed lane layout: `knowledge/` (written entries + topic docs, with `knowledge/inbox/` for fresh ones), `inbox/` (ingested documents as normalized Markdown), `rules/`, `handoff/`, `superseded/`, and `.raw/` (ingested originals). `.raw/` MUST be dot-prefixed: grep runs over the whole scope directory and ripgrep skips hidden entries, so an ingested original never returns as a second hit alongside the Markdown converted from it. Path construction MUST live in exactly one module (`infrastructure/knowledge/paths.py`) and every name that becomes a path segment MUST pass a traversal guard.
- **FR-003**: `coffer__write` (and a user add) MUST append an entry to the scope's `knowledge/inbox/` with no LLM at write time; organization into topic documents is asynchronous (FR-027) and never blocks the write or retrieval.
- **FR-004**: System MUST resolve the per-project scope from the agent's reported launch cwd at session handshake: the daemon computes the git-root and resolves — lazily provisioning if absent — the scope for that project's ULID.
- **FR-004a** (spec 010 / ADR-043 amendment): the project ULID MUST be **machine-portable** — derived from the normalized `origin` remote URL when the repo has one (ssh/https/scp-like forms of the same repository normalize identically), falling back to the absolute-git-root-path hash for repos without a remote. The same repository therefore resolves to the same scope on every synced machine, whatever its checkout path. A scope provisioned under the legacy path-derived id is adopted **once** on first resolve: its files move to the portable id's dir, the resource is re-registered under the new name, and the root mapping and display label carry over.

**Entry lifecycle**

- **FR-005**: Agents and users MUST be able to write an entry directly (no LLM at write time). Entry text MUST be at least 1 char and at most `max_entry_chars` (per-scope default 8192, hard ceiling 32768); empty or over-long text is rejected at the API boundary with nothing persisted. The per-scope default bounds ordinary agent writes; a trusted bulk import of the user's own notes may go up to the ceiling so a long note is never silently truncated.
- **FR-006**: Users and agents MUST be able to list entries (per scope), get one by id, edit its text, delete one, and clear a scope. Clearing preserves the scope Resource. The Coffer UI renders entry content read-only and does not edit it in-app; humans curate through the REST/CLI write surface or their own external editor.
- **FR-007**: Every entry carries `metadata.actor` (`agent` | `user`); the writer sets it. There is **no free-form `type` field** — `Lane` is the single classification axis (FR-048), determined by internal routing (the organizer), never supplied by the writer.

**Retrieval**

- **FR-008**: Retrieval MUST use one engine over the whole scope: `grep` (ripgrep over the scope's files; essential for content FTS5 cannot tokenize, e.g. CJK), `keyword` (FTS5 BM25 over a trigram tokenizer, the default), `vector` (sqlite-vec against the installation-wide embedding provider), and `hybrid` (reciprocal rank fusion of keyword + vector). These modes are an **internal detail** ([ADR-034](../../docs/decisions/ADR-034-retrieval-mode-is-internal.md)) — no external surface takes a `mode`; the engine resolves the scope's default strategy automatically (`hybrid` when the scope lists vector, else `keyword`). When the resolved strategy needs vectors but no embedder is available, retrieval MUST fall back to `keyword` internally — never block, and never surface a query-time `fallback` flag.
- **FR-008a**: Retrieval MUST span **both lanes** of a scope. A search returns the entries an agent wrote and the documents a human ingested, ranked together. Lane-scoped reads (the documents listing, `entry_count`/`document_count`) exist for presentation and curation; they MUST NOT partition retrieval. Unified search is the reason the two kinds merged, so re-splitting it one level down would defeat the change.
- **FR-009**: `coffer__search` MUST default to spanning the current project's scope and `global` (an explicit `scope` narrows to one). Cross-scope results are merged by reciprocal rank fusion — per-scope scores are not comparable, so each hit keeps its own score and only the merged order comes from the fusion. Results carry id, text, score, source, and time. Default `top_k` is 5; callers MAY specify 1–20.
- **FR-010**: The layer MUST use **lazy reindex-on-read**: a read or search first scans for deltas (added/changed/removed files by content hash) and reconciles the index before serving, so out-of-band edits — a human's corrections in their own editor, or any direct on-disk edit — are visible immediately with no filesystem watcher. This is what lets the UI stay a read-only viewer (FR-017) while curation happens in the user's editor.

**Agent integration via MCP**

- **FR-015**: Coffer's MCP gateway MUST expose **eight** built-in knowledge tools under the reserved `coffer__` prefix:
  - `coffer__search(query, scope?, top_k?)` — ranked snippets across both lanes (replaces `coffer__recall` and `coffer__search_knowledge`)
  - `coffer__grep(pattern, scope?, max_matches?)` — literal/regex file+line matches (replaces `coffer__grep_knowledge`)
  - `coffer__read(id, scope?)` — one item in full, entry or document, resolved automatically (replaces `coffer__read_document`)
  - `coffer__list(scope?, all?, limit?)` — a scope's contents, or the catalogue of every scope (replaces `coffer__list_memory` and `coffer__list_knowledge_bases`)
  - `coffer__write(text, title?, description?, filename?, id?, scope?)` — files an entry from `text`, stores a document when given `filename`, rewrites either in place when given `id` (replaces `coffer__remember`, `coffer__add_document` and `coffer__edit_document`)
  - `coffer__delete(id, scope?)` — removes one entry or document (replaces `coffer__delete_document`)
  - `coffer__set_handoff(body)` and `coffer__resume()` — unchanged
  Each of the first six MUST take an optional `scope`, defaulting to the cwd's project scope and falling back to `global` outside a project. No tool takes a retrieval `mode`. The caller MUST never have to decide whether something is "memory" or "knowledge" before choosing a tool — that guess is what the twelve-tool surface forced and what eight verbs removed.
- **FR-016**: Built-in tool invocations MUST share the existing invocation-logging surface (one `mcp_invocations` row: tool name + who/when/duration/outcome only — no arguments or returned content). The document-level effect of a write tool is additionally recorded in the F01 audit trail with the agent as actor.

**Working-state handoff (continuity)**

- **FR-023**: The system MUST provide a **working-state handoff** lane keyed by **(project scope × git branch)**: one file per branch under `~/.coffer/knowledge/project-<ULID>/handoff/<branch-slug>.md`, with YAML frontmatter (`branch`, `updated_at`) plus a freeform Markdown body. The branch is resolved from the agent's reported cwd. Handoff is **per-project only** — there is no global handoff.
- **FR-024**: `coffer__set_handoff(body)` MUST **overwrite** the current branch's handoff file (one scene per branch), set `updated_at`, and record a `handoff_set` audit entry. The body is files-as-truth on disk and MUST NOT be returned by `coffer__search` (it lives outside the retrieval glob).
- **FR-025**: `coffer__resume()` MUST return the current branch's saved handoff — `found=true` with `branch`, `body`, `updated_at`, and a freshness `note` annotating that the scene may be stale — or `found=false` when no handoff exists for the branch or the cwd is not inside a git project. It MUST never error on a missing handoff and MUST NOT fabricate content.
- **FR-026**: When the agent's cwd does not resolve to a git project, `coffer__set_handoff` MUST be rejected and `coffer__resume` MUST return `found=false`.

**Consolidation — the internal organizer**

- **FR-027**: The system MUST provide an **internal organizer** that drains a scope's `knowledge/inbox/` into a small set of coherent **topic documents** (`knowledge/<topic-slug>.md`) using Coffer's **internal LLM connection** (the connection marked internal-default; Settings → LLM Connections, spec 011) via a **one-shot completion per item** — never an agent-facing tool. It is triggered explicitly (`POST /api/v1/knowledge/{scope}/organize`, `coffer knowledge organize <scope>`) and automatically on idle (FR-035). Items process sequentially, and one item's LLM/parse failure MUST NOT abort the run.
- **FR-028**: For each inbox item the organizer MUST (a) retrieve up to the top-K (K=3) most-relevant **existing topic docs** via the shared retrieval engine (no LLM on this step) as merge candidates, (b) make **one LLM call** that either MERGES the item into the best-fitting candidate — **preserving all existing content and human edits**, integrating the new information, removing exact duplicates — or CREATES a new topic when none fits, and (c) write the returned full document body to `knowledge/<topic-slug>.md`. It MUST be an **incremental merge, never a from-scratch regeneration**, and MUST NOT hard-delete an existing topic doc.
- **FR-029**: An inbox item MUST be **deleted only after** its content is successfully written into a topic doc. A malformed or unparseable LLM response MUST cause that item to be **skipped** — left in the inbox, no topic doc written or corrupted — and the run continues; the result reports the skipped count. `organize` on an empty inbox is a no-op (`status="empty"`); with no internal connection configured it is a clean no-op (`status="no_model"`) rather than an error.
- **FR-030**: After draining, the organizer MUST regenerate the scope's `knowledge/INDEX.md` catalogue from all topic docs' frontmatter, reconcile the index (dropping the drained inbox rows and (re)indexing the new/updated topic docs), and record one `memory_organized` audit entry (scope + counts only — no item content). Retrieval MUST surface organized topic-doc content and MUST NOT surface `INDEX.md`.
- **FR-031**: The organizer MUST keep a **non-blocking consolidation changelog** at the scope root (`consolidation-log.md`, append-only, human-readable: one line per merged/created topic with the timestamp and the source inbox item). It is auditable, never a gate, and is **excluded from retrieval** (it lives outside the `knowledge/` lane) and from the sync mirror (machine-local, like `INDEX.md`; topic docs themselves DO sync as source-of-truth).
- **FR-032**: The reconciler MUST chunk a file's body into **passage-granular, structure-aware chunks** using the shared Markdown chunker (`infrastructure/knowledge/chunking.chunk_markdown` — splits on heading sections, keeps fenced code / tables atomic, packs structural blocks up to a fixed window), so a multi-section topic document surfaces the **most relevant passage** rather than its entire body. A short single-passage item still chunks to one passage: this changes **granularity**, never *what* retrieval includes or excludes.
- **FR-033**: The system MUST provide an **internal agentic reorganization pass** (`POST /api/v1/knowledge/{scope}/reorg`, `coffer knowledge reorg <scope>`; explicit trigger only) running a bounded **langgraph `create_react_agent` loop** driven by the internal LLM connection over the scope's topic documents — consolidating duplicates and splitting over-long ones. Its fixed tool surface is **list / read / write / supersede** over topic docs, and it is **never agent-facing**. langchain/langgraph code MUST stay confined to `infrastructure.chat` (importlinter Contract 9); `application/knowledge` reaches it only through an injected port. With no internal connection it is a clean no-op (`status="no_model"`); a scope with no topic documents is likewise a no-op (`status="empty"`). Afterwards the pass regenerates `INDEX.md`, reconciles the index, and records one `memory_reorganized` audit entry.
- **FR-034**: The reorg pass MUST be **non-destructive and incremental**. Every mutation that removes or replaces existing topic-doc content MUST first **archive the current version** to the scope-root `superseded/` tombstone (`superseded/<slug>-<timestamp>.md`): a `write` that overwrites archives the prior version first, and a `supersede` **moves** the document there. The tombstone is **excluded from retrieval** and **DOES sync** as recoverable history. Topic-doc writes remain **atomic**, and every write/supersede is appended to `consolidation-log.md`. This is the data-loss guarantee: no byte leaves the `knowledge/` lane without first being recoverably archived.
- **FR-035**: The system MUST provide an **auto idle organize trigger** that fires `organize` (FR-027) automatically in the background when a scope goes idle — approximating "session end" without a per-agent disconnect signal. Each knowledge write (re)arms a single **debounced** timer; after the idle delay elapses with no further writes the organizer runs for the changed scope(s) as a background task. It MUST be **conservative and non-blocking**: (a) **default-ON**, controlled by an environment off-switch; (b) it MUST NEVER block or break daemon shutdown — a pending timer is cancelled and the un-fired inbox left intact (nothing is lost: retrieval already covers the inbox and `organize` is idempotent); (c) a background-pass failure MUST be suppressed + logged; (d) with no internal connection it is a clean no-op. It introduces **no new REST/CLI surface** and reuses the `memory_organized` audit.
- **FR-036**: The system MUST provide a **procedural `rules` lane** — `rules/rules.md` per scope — holding "do this / don't do that" behavioural rules. The lane stays a single file while small; once any `rules/*.md` exceeds **100 rules**, the organizer classifies its rules by topic via a one-shot LLM call and redistributes them into per-category `rules/<slug>.md` files (applied recursively). New rules keep appending to `rules/rules.md`; the read surface concatenates **every `rules/*.md`**. The lane is **agent-written via the organizer's classification, never an explicit agent parameter**: during `organize` the per-item LLM call MAY classify an inbox item as a **rule**, which is **appended** to `rules/rules.md` (the inbox item drained only after the append succeeds) instead of merged into a topic document, and the result/audit reports a `rules_appended` count. The `rules/` lane sits at the scope ROOT so it is **excluded from retrieval** for free — a rule is a standing instruction, not a search hit. It is read **on demand through its own surface**, and **nothing pushes it into an agent session**: the system MUST expose the stored rules read-only over `GET /api/v1/knowledge/{scope}/rules` and `coffer knowledge rules <scope>`, returning the rules text (empty/`null` when there are none, never an error), and that read is the only way the lane leaves disk. The lane is source-of-truth and DOES sync.

**Lane taxonomy**

- **FR-048**: The free-form `type` field is **retired** — `Lane` (`knowledge` / `rules` / `handoff`) is the **single classification axis** for written items. The system MUST NOT carry a `type` field on the entry entity, in file frontmatter (`metadata.type`), in the `documents.metadata` JSON, in the `coffer__write` tool schema, or in the REST/CLI write surface. An item's lane is determined by **internal routing** (the organizer), never supplied by the writer.

**Delivery — removed**

The rules lane has an **ingest** half and no **delivery** half. Knowledge still
goes in — an agent writes, the organizer classifies, rules land in `rules/*.md`
and sync — but nothing carries it back out to a session on its own.

Until 2026-09-10 it did. **FR-049** delivered the lane through a Coffer-installed
`coffer-hook` SessionStart hook (`GET /api/v1/agents/{name}/session-context?cwd=`
→ `additionalContext`, never a native file write); **FR-050** added two
Coffer-seeded built-in rules to that bundle (call `coffer__resume()` to continue
prior work; prefer Coffer's shared knowledge tools over the agent's native
memory); **FR-052** offered an opt-in per-agent `disable_native_memory`
cleanliness switch; **FR-055** appended a title-only project-knowledge index so
an agent started knowing what the project held. All four are **deleted**, along
with the binary, the hook install/uninstall surface, the `session-context` route,
the bundle assembler and the digest renderer.

**The cost, stated plainly.** This removes the delivery half of cross-agent
memory. An agent must now call `coffer__recall` / `coffer__search` itself; it
will **not** be told what the project knows unless it asks, and the rules the
user accumulated sit on disk until something goes looking for them. Search
discipline — the exact thing ambient injection existed to not depend on — is
now load-bearing.

**Why that is accepted.** The hook shipped, but it was never actually installed
on this user's machine, so the injection path had never run in practice. What
was removed is a capability on paper that no session had ever exercised, and
keeping it meant keeping a second frozen binary, a hooks-file writer for two
agent formats, an agent-scoped HTTP route and a budget-bounded bundle assembler
alive for it. Re-introducing ambient delivery is a deliberate future decision,
not an oversight.

**Surfaces**

- **FR-017**: Users MUST be able to perform full knowledge CRUD through (a) a REST API under **`/api/v1/knowledge`**, with the scope as a path segment and `entries` / `documents` as sub-resources, and (b) the **`coffer knowledge`** CLI group — one group of 31 subcommands replacing the former `coffer memory` and `coffer kb`. User writes set `metadata.actor = "user"`, write the canonical Markdown, reindex, and audit. The web UI surfaces content **read-only**; humans curate in their own external editor (picked up by lazy reindex-on-read, FR-010) or via REST/CLI. The read-only viewer MUST render content at a comfortable reading **max-width** (centered), and detail-page lists MUST be single **scrollable** lists with no in-UI pager (the UI fetches one page at the max `limit`; the APIs stay paginated by `limit`/`offset`). Scope names on these surfaces are validated per FR-002: a well-formed `global` or `project-<26-char ULID>` lazily provisions; any other name must already exist or the request is a 404.
- **FR-017a**: Surfaces MUST present a per-project scope by a **human-readable identity derived from its `project_root`** — the root directory's basename as the primary label and the absolute root path as a secondary detail — never only the opaque `project-<ULID>` name. When the root is unknown the surface falls back to the scope name; `global` and named collections are already readable. This is a **display** concern; the underlying name stays `project-<ULID>`.
- **FR-017c**: A user MUST be able to set a **display label** for any scope, taking precedence over the FR-017a derivation. Setting an empty / whitespace label clears it. The label is display metadata: it does not change the scope name or `project_id`, and is set via `PATCH /api/v1/knowledge/{scope}/label`. Labels are stored in the machine-local `knowledge_scope_labels` table (renamed from `memory_store_labels` by migration 0051, its key column `store_name` → `scope_name`).
- **FR-017d**: `PATCH /api/v1/knowledge/{scope}` MUST **merge** the submitted fields into the scope's existing config (`exclude_unset`), not replace it. A caller that sends only `chunk_size` must not silently reset `retrieval_modes`. (This reverses spec 006's earlier "the backend replaces, not deep-merges" position, which the merged implementation does not follow.)
- **FR-017e**: There MUST be **no** `DELETE /api/v1/knowledge/{scope}`. Deleting a scope goes through the kind-agnostic Resource framework (`DELETE /api/v1/resources/knowledge/{name}`), which cascades documents, chunks, index rows and the on-disk directory. Scope lifecycle is a Resource concern; the knowledge router owns only what is specific to knowledge.
- **FR-021**: The read-only viewer MUST offer, for both a file and its containing folder, affordances to (a) **open in external editor** and (b) **reveal in file manager / Finder**, performed through the loopback daemon's filesystem-action endpoints (spec 004 FR-039) since the daemon is on the user's own machine ([ADR-033](../../docs/decisions/ADR-033-daemon-proxies-os-file-actions.md)). There is no copy-path fallback. Which editor opens is the global preferred-editor preference (002-ui-shell).
- **FR-022**: Read responses MUST surface the on-disk truth: entry and document read endpoints MUST include each file's absolute `.md` path and its containing folder's absolute path, and the scope read endpoint MUST include the scope's absolute on-disk directory.
- **FR-053**: The Knowledge detail page MUST present a scope as **five tabs** — **Entries**, **Documents**, **Rules**, **Handoff**, **Changelog**. Each gets a shape-fit view: Entries and Documents are trees plus content, Rules is a single document, Handoff is a per-branch list, Changelog is an append-only log. All views are **read-only**, render via the **unified file preview** (no hand-styled `<pre>`), and offer **open in external editor / reveal in file manager / copy path** on the underlying file. The Entries/Documents split is presentational (FR-008a): retrieval still crosses both.
- **FR-053a**: The web UI MUST route the layer at **`/knowledge`** and **`/knowledge/:scope`**, and MUST keep the pre-merge URLs working as redirects: `/memory` and `/knowledge-bases` → `/knowledge`; `/memory/:name` and `/knowledge-bases/:name` → the corresponding `/knowledge/:scope`. Bookmarks predate the merge; breaking them would be a gratuitous cost.
- **FR-054**: The system MUST expose read endpoints for the lanes the UI needs: `GET /api/v1/knowledge/{scope}/handoff` (scenes per branch, each with `branch` and `updated_at`) and `GET /api/v1/knowledge/{scope}/consolidation-log` (`null` when absent). These are **read-only**, **addressed by scope name** (not cwd), and MUST return **HTTP 200 with empty lists / `null`** for an empty scope, never a 404. (Rules already has `GET /api/v1/knowledge/{scope}/rules`, FR-036.)

**Scope consolidation — AI-assisted**

- **FR-056**: The system MUST provide an explicit **merge scan** — `POST /api/v1/knowledge/merge_scan` and `coffer knowledge merge-scan` — examining every pair of per-project scopes and returning merge proposals. A pair whose locally-readable roots normalize to the **same non-empty origin remote** (FR-004a normalization) is proposed deterministically (`confidence="certain"`, `judged_by="remote"`) with no LLM involved; every other pair is judged by the **internal engine** via one one-shot completion returning a strict JSON verdict `{same_project, confidence, reason}` — a malformed response skips the pair, never errors. With no internal engine the scan returns `engine="no_model"` and the deterministic proposals only. The engine tier is bounded (at most 50 judged pairs per scan, `truncated=true` when capped; evidence samples size-capped). Each proposal carries a suggested direction: the scope with a locally-resolvable root survives, then the higher item count, then the lexically smaller name. Scanning never mutates anything.
- **FR-057**: The system MUST provide an explicit **merge execution** — `POST /api/v1/knowledge/merge` with `{source, target}` and `coffer knowledge merge <source> <target>` — consolidating two per-project scopes additively: derived files skipped, any collision keeping both copies (suffixed) — knowledge is gained, never lost. The source's display label and `project_root` mapping move to the target when the target lacks its own. The target is force-reconciled, the source scope is retired (resource delete cascading documents/index/dir), and one `memory_stores_merged` audit entry (names + counts only) is recorded. `source` and `target` MUST be distinct, existing, **per-project** scopes — `global` and named collections are never mergeable; violations are 4xx with no side effects. Merge execution serializes with resolve-time adoption on the same lock; writes do not hold that lock, so the merge re-sweeps the source immediately before retirement (the file merge is content-idempotent).
- **FR-058**: A merge MUST leave a **no-resurrection alias**: the surviving scope's config gains `merged_identities` (a system-managed list of project ULIDs, default empty) holding the source's ULID plus the source's own aliases (transitive across chained merges). The scope resolver MUST consult the aliases **only when the computed identity's scope does not exist** and resolve to the aliased survivor instead of re-provisioning an empty duplicate. Exactly one live scope holds a given alias, and the boot consolidation pass MUST honour the aliases the same way. Because the alias lives in `config_json`, it syncs with the resource so the redirect holds on every machine.
- **FR-059**: Merge execution MUST accept `organize` (default `true`): after a successful merge, when the internal engine is configured, the FR-033 reorg pass runs on the target and its outcome is reported as `reorg_status` (`"reorganized"`, `"no_model"`, `"empty"`, `"skipped"`, or `"error: …"`). A failed or unavailable organize step never fails the merge itself.

**Ingestion & conversion** *(folded in from spec 006)*

- **FR-060** *(was 006 FR-004/FR-005)*: Users and agents MUST be able to add a file of any supported format; the system MUST detect format, convert to Markdown via a pluggable `MarkdownConverter` port, clean the output, prepend YAML frontmatter, write `inbox/` + `.raw/`, and index it. Conversion MUST dispatch through a per-format converter registry confined to `infrastructure/`: Markdown/text/source files pass through unchanged, `csv` has a dedicated converter, and everything else (pdf / docx / pptx / xlsx / xls / html / epub / …) goes through the default MarkItDown engine (`markitdown[docx,pdf,pptx,xls,xlsx]`). Formats MarkItDown has no converter for (legacy binary `.doc`/`.ppt`, `.rtf`, `.odt`) are rejected as `unsupported_type`, not advertised. A higher-fidelity engine for a format is a new converter in the registry, not a substrate change.
- **FR-061** *(was 006 FR-006)*: The system MUST reject files over `max_document_bytes` (default 25 MB, configurable per scope), files of unsupported type, and files whose conversion yields empty Markdown — a PDF converting empty is rejected specifically as `scanned_pdf` so the UI can say something actionable.
- **FR-062** *(was 006 FR-007)*: Each ingested document MUST be identified by a **stable ULID** minted at first ingest (not a content hash). The system MUST compute `source_sha256` of the original (kept in `metadata` as provenance) and match a re-upload to an existing document by `original_filename` within the scope: a **byte-identical** re-upload is an idempotent no-op; a **changed** re-upload of a filename already present updates the **same document in place** (reusing the id) only when `replace=true`, otherwise it is rejected (`duplicate`); a **new** filename is a new document. The same file ingested into two scopes yields two independent documents — documents are not deduplicated across scopes.
- **FR-063** *(was 006 FR-010a)*: Listing documents MUST support an optional **case-insensitive title filter `q`**, applied server-side BEFORE pagination; `total` reflects the filtered count.
- **FR-064** *(was 006 FR-011/FR-011b)*: The keyword index MUST use an FTS5 **trigram** tokenizer so CJK and substring queries match — `unicode61` does not segment CJK text, so a query like `向量检索` returned nothing; a query with no token of ≥ 3 characters falls back to a bounded substring (LIKE) scan rather than returning empty. Grep responses carry a `truncated` flag, true when matches beyond `max_matches` exist OR the server-side timeout cut the scan short (a timed-out grep returns no hits with `truncated=true`, and the `rg` process is killed). `hybrid` MUST run BOTH keyword and vector searches and fuse them by **reciprocal rank fusion**: each passage's fused score is `Σ 1/(K + rank)` with `K = 60` and `rank` the 0-based position in that list; passages are deduped by chunk identity `(document_id, position)` so a passage in both lists sums both contributions and outranks single-list hits.
- **FR-065** *(was 006 FR-014)*: Chunk parameters MUST be mutable per scope; changing them re-chunks and re-indexes. The embedding model is mutable installation-wide; changing it re-embeds every scope that lists a vector mode. There is NO immutability lock on these fields.
- **FR-066** *(was 006 FR-015/FR-016)*: Each ingested document MUST carry a `source_mode` of `converted` (Markdown derived from the original, re-convertible) or `edited` (re-conversion blocked). All write paths — re-upload, edit API, agent `coffer__write`, external edit, reindex scan — MUST funnel through **one idempotent re-index routine**, invoked lazily on read when the on-disk `content_sha256` has drifted: unchanged is a no-op; changed deletes old chunks/FTS5/vec rows, re-chunks, re-embeds (if vector is enabled), updates the `documents` row, and audits `KB_DOCUMENT_UPDATED`. Documents are co-managed: both humans and agents may add, edit and delete, and every agent write is audited with the agent as actor.
- **FR-067** *(was 006 FR-021)*: A **path-based** ingest (the CLI, and a native file picker in the web UI) MUST record the external original's **absolute path** in the document's free-form `metadata` as `source_path` — no schema migration; it rides the existing JSON. A byte-upload and an agent `coffer__write` MUST NOT set or infer `source_path` (an untrusted surface must never populate an arbitrary server path). `source_path` is machine-local.
- **FR-068** *(was 006 FR-022)*: `check-sources` MUST classify each path-tracked document by re-hashing the external file with sha256 — streamed in chunks so a multi-GB original is never read fully into memory — and comparing to the stored `source_sha256`: `unchanged`, `changed`, or `missing`. Detection is **on-demand only** (no filesystem watcher); detect-only changes nothing and audits nothing.
- **FR-069** *(was 006 FR-023)*: `update-source` MUST re-ingest a document from its `source_path` in place — replaying the `replace=true` re-ingest path, so the stable ULID is preserved and the scope re-chunked/re-indexed (audited via `KB_DOCUMENT_UPDATED`). A document whose `source_mode == edited` MUST be refused so hand edits are never clobbered; a vanished or untracked source is reported via `IngestRejected`.
- **FR-070** *(was 006 FR-024)*: A per-scope `auto_update_sources` flag (default **false**) governs `check-sources`: when false, detection only classifies; when true, each `changed` document whose `source_mode != edited` is auto-refreshed in place (reported `updated`), while a `changed` hand-edited document is skipped (reported `edited`). Toggling the flag MUST NOT re-chunk or re-embed — it is not a reindex-triggering field.
- **FR-071** *(was 006 FR-025)*: When an embed degrades because the embedding provider is unavailable (`EngineUnavailable`), the document MUST be indexed keyword-only and its retry state tracked on a dedicated persisted `embed_pending` flag — decoupled from `content_sha256`, which MUST always carry the real body hash. The scope MUST surface the count of such documents as `documents_degraded` in its metrics, computed from the persisted flag so it reflects a degrade observed during **any** read. The next reconcile MUST retry **only** the embed for a still-pending document whose body is unchanged — re-chunking in memory and upserting only the vectors, clearing `embed_pending` on success.

**The merged model itself** *(new with the 2026-09-10 merge)*

- **FR-072**: One resource kind `knowledge` MUST replace the former `memory` and `knowledge_base` kinds across every surface: the Resource framework, REST, CLI, the web UI, and the MCP tool list. No surface may reintroduce a "which kind is this?" question.
- **FR-073**: The `documents` table MUST carry a stored **lane discriminator** `documents.lane` (`knowledge` for an entry a writer filed, `inbox` for an ingested document), with an index on `(kind, resource_name, lane)`. It MUST be **stored, not derived from the path**, because the paths genuinely overlap: an entry lives at `<scope>/knowledge/inbox/<id>.md` and an ingested document at `<scope>/inbox/<id>.md`, and the storage root is itself `~/.coffer/knowledge/`, so no path predicate separates them — and anchoring on the scope directory would push knowledge-lane layout into the kind-agnostic repository that serves every kind. `entry_count` and `document_count` MUST be lane-scoped; retrieval MUST NOT be (FR-008a). The lane is an internal storage concern and is **not** exposed on the wire: the endpoint a caller used already implies it, so putting it on the document payload would only invite a client to filter on it.
- **FR-074**: The per-scope config (`KnowledgeConfig`) MUST be the union of what the two former configs actually used — `retrieval_modes`, `default_mode`, `max_entry_chars`, `chunk_size`, `chunk_overlap`, `max_document_bytes`, `auto_update_sources`, `merged_identities` — and MUST carry **no embedding fields at all**. Both former configs had them (`embedding_*` flat on memory, a nested `embedding` block on the knowledge base) and by the time of the merge **neither was read**: embedding resolves through the installation-wide config, and a scope opts into vector search purely by listing the retrieval mode. Dead fields are dropped rather than carried across. Enabling `vector` MUST also enable `hybrid` and make it the default unless the caller chose one explicitly.
- **FR-075**: Migration `0051` MUST merge the two kinds into `knowledge`, **clear** the derived index rather than convert it, and rename the two machine-local side tables (`memory_store_project_roots` → `knowledge_scope_project_roots`, `memory_store_labels` → `knowledge_scope_labels`, key column `store_name` → `scope_name`). Migration `0052` MUST add `documents.lane` and its index, backfilling on the entry lane's distinctive `knowledge/inbox/` nesting (matching a bare `knowledge/` segment would be wrong — the storage root contains it). Clearing rather than converting is required, not merely convenient: `memory:global` and `knowledge_base:global` both existed and `resources` is keyed by `(kind, name)`, so converting both would collide and any automatic rename would be a guess; and every `documents` row indexed the journal lane removed one revision earlier, so the index pointed at files that no longer exist. Both migrations MUST be guarded so a database missing any of these still upgrades.

**Substrate isolation & migration**

- **FR-018**: The retrieval/index engine (FTS5, sqlite-vec, embedding providers, converters) MUST be confined to infrastructure. Domain and application layers MUST NOT import index/engine types directly; interaction is via the shared retrieval port. mem0, chroma, and LlamaIndex MUST NOT be imported anywhere.
- **FR-019**: Legacy on-disk engine directories (chroma/LlamaIndex) from pre-release builds are abandoned in place — nothing reads them — rather than deleted. Legacy per-item files at a scope root from pre-lane builds are likewise abandoned in place: lazy reindex-on-read reconciles the `knowledge/` lane, so stale index rows are reconciled away on the next read.

### Key Entities

- **Knowledge Scope** (a resource of kind `knowledge`): one of `global`, `project-<ULID>`, or a named collection — the kind derived from the name. Config = `retrieval_modes`, `default_mode`, `max_entry_chars`, `chunk_size`, `chunk_overlap`, `max_document_bytes`, `auto_update_sources`, `merged_identities`. No embedding fields.
- **Document** (one Markdown file = one `documents` row, `kind="knowledge"`): id (stable ULID), scope resource name, `lane` (`knowledge` | `inbox`), on-disk path, title, description, `content_sha256` (always the real body hash), `embed_pending` (index-derived retry flag, not file-truth), `source_mode`, `project_id`, per-writer `metadata` (ingest: `original_filename`, `original_format`, `source_sha256`, `converted_at`, `conversion_engine`, optional `source_path`; entry: `actor`, `origin_session_id`), timestamps.
- **Chunk** (`chunks` row): position within a document. The chunk text is stored once inside the FTS5 index, not duplicated into a base table; it stays rebuildable from the Markdown files.
- **Passage** (retrieval result, not persisted): passage text, source id, title, score, position.
- **Grep hit** (retrieval result, not persisted): path, line number, line.
- **Handoff scene** (one file per `(project scope × branch)`): branch, body, `updated_at`.

## Success Criteria

### Measurable Outcomes

- **SC-001**: An item written by one agent via `coffer__write` is found by a different agent via `coffer__search` in the same project within one session, with no per-agent copy diverging.
- **SC-002**: One `coffer__search` over a scope holding both a written entry and an ingested document returns hits from both, with no lane parameter and no second call.
- **SC-003**: With 200 items in a scope, search latency for a typical keyword query is ≤ 300 ms wall-clock on a developer laptop; with a 50-document scope (≤ 50 MB), keyword search is ≤ 200 ms and grep ≤ 500 ms at the REST surface.
- **SC-004**: Default retrieval works offline with zero configuration (keyword + grep); vector is opt-in and degrades to keyword when unconfigured — it never errors.
- **SC-005**: `coffer knowledge reindex <scope>` rebuilds all SQLite index state purely from the Markdown files (drop the rows, reindex, search returns identical results).
- **SC-006**: Every Acceptance Scenario is covered by at least one test marked `acceptance(spec="007-memory", scenario="…")`; `make verify-acceptance` reports zero uncovered scenarios and zero orphaned markers.
- **SC-007**: Substrate isolation is enforced by importlinter: no module under `coffer.application.*` or `coffer.domain.*` imports the index engine, `markitdown`, `sqlite_vec` or an embedding-provider SDK, and `mem0`/`chroma`/`llama_index` are imported nowhere.
- **SC-008**: Deleting a scope removes 100% of its on-disk footprint and 100% of its SQLite rows.
- **SC-009**: An MCP client sees exactly eight knowledge tools, and none of them requires the caller to classify an item as "memory" or "knowledge" before choosing.
- **SC-010**: `make verify` passes locally and in CI.

## Assumptions

- The user runs Coffer on their own machine; knowledge data stays local. Calling a configured cloud embedding provider for opt-in vector retrieval is allowed (local-first ≠ no remote API calls).
- The canonical format is per-item Markdown files (YAML frontmatter + body) under `~/.coffer/knowledge/<scope>/`; there is no derived index file that retrieval reads.
- The coffer-mcp-shim propagates its launch cwd to the daemon at session handshake on the supported agents.
- Keyword + grep are zero-config and offline; vector retrieval reaches a configured embedding provider, which MAY be a third-party API.
- `ripgrep` is available on supported platforms (macOS arm64, Linux); sqlite-vec loads as a SQLite extension on those platforms.
- Single-user concurrency is small.

## Notes for reviewers

- **This spec is the merge of 006 and 007.** `specs/006-knowledge-base/` was deleted when its surviving content landed here. Its acceptance-scenario headings were carried over verbatim so their existing test markers keep matching; only the `spec=` argument changed from `"006-knowledge-base"` to `"007-memory"`.
- **The directory name is historical.** `specs/007-memory/` is the spec id that `scripts/audit_acceptance.py` keys on and that every inbound link uses. Renaming it would break both for no gain.
- **Retrieval mode stays internal** ([ADR-034](../../docs/decisions/ADR-034-retrieval-mode-is-internal.md)). Nothing here re-opens that.
- **ADR-028 (co-managed documents) and ADR-030 (per-project KB scope + soft delete) were deleted**, absorbed into this spec: co-management is simply how the one knowledge kind works, and per-project scope is now the scope model itself. Recoverable soft-delete for documents remains unbuilt — deletion is a hard delete with an F01 audit trail; the `superseded/` tombstone (FR-034) covers only the organizer's own rewrites.
- **Embedding default**: vector is opt-in; the zero-config default is `keyword` + `grep` (offline, language-agnostic). For bilingual corpora a local `bge-m3` or a cloud provider is recommended.
- **Deferred**: reranking / HyDE / multi-query / LLM synthesis on retrieval; recoverable soft-delete for documents; an in-app Markdown editor (the viewer stays read-only with external-editor affordances); image OCR by default; a filesystem watcher on by default.
