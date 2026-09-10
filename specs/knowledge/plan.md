# Implementation Plan: Memory (Shared Agent Memory)

> 中文版: [plan.zh.md](./plan.zh.md)

> **Historical — 2026-09-10.** The Knowledge Base and Memory specs merged into
> one **Knowledge Layer** on this date. [`spec.md`](./spec.md) is the
> authority for the merged model — one `knowledge` kind, three scopes, one
> storage root `~/.coffer/knowledge/<scope>/`, eight `coffer__*` tools. This
> document records the design as it stood before that merge; where it says
> "memory face", "`memory` kind", `~/.coffer/memory/`, `/api/v1/memory_stores`
> or `coffer memory …`, read the merged equivalents in `spec.md`. The folder
> name `specs/knowledge/` is likewise historical: it is the spec id every
> inbound link and the acceptance audit key on.

**Branch**: `feature/kb-memory-redesign`
**Spec**: [./spec.md](./spec.md)
**Status**: Accepted (redesign — in development)

---

# 2026-09-11 Redesign — Two Lanes

**Status**: design approved, implementation not started. Everything below
supersedes the corresponding parts of the historical plan that follows it.

## Why

A knowledge scope currently keeps seven lanes on disk and the detail page shows
five of them as equal-weight tabs — Entries, Documents, Rules, Handoff,
Changelog. Those are *storage lanes*, not categories a person recognises, and
the mismatch shows:

- Two directories are both called an inbox. `knowledge/inbox/` holds freshly
  written entries; `inbox/` holds ingested documents. The UI calls the first
  "Entries" and the second "Documents", so the shared name explains nothing and
  the different names explain the wrong thing.
- The Entries tab flattens two unlike things into one list: raw items an agent
  just wrote, and the topic documents the organizer merged them into.
- The Rules lane lost its delivery channel on 2026-09-10 (FR-049/050/052/055).
  Rules are still written and stored; nothing reads them.
- Changelog is an audit trail of the organizer, not content — and the organizer
  can only be triggered from the CLI, so the page shows the by-product of a pass
  it offers no way to run.

There are only two kinds of material a person actually distinguishes: what
someone wrote, and what someone uploaded.

## On-disk layout

```text
~/.coffer/knowledge/<scope>/
├── notes/       # what an agent or the user wrote (coffer__write lands here)
├── docs/        # uploaded documents, normalized to markdown
├── .raw/        # the uploaded originals (hidden)
└── .history/    # note revisions the tidy pass replaced (hidden)
```

Two lanes. `knowledge/inbox/` and its topic-document gradient are gone: a note
is a note whether it was just written or has been tidied since.

`.history/` sits at the scope root beside `.raw/` rather than inside `notes/`.
Nesting it in the lane would oblige the lane scan, the reindex and every future
reader of `notes/` to remember to skip it; as a sibling it is simply another
hidden archive under the one rule that already governs `.raw/` — ripgrep skips
hidden entries, so `coffer__grep` never returns an original or a replaced
revision beside the live file.

## Migration

Destructive, by explicit instruction — no `.retired/` holding pen:

| Now                                              | After                     |
| ------------------------------------------------ | ------------------------- |
| `knowledge/inbox/*.md` + `knowledge/*.md`        | flattened into `notes/`   |
| `inbox/`                                         | `docs/`                   |
| `.raw/`                                          | unchanged                 |
| `rules/`, `handoff/`, `superseded/`              | **deleted**               |
| `consolidation-log.md`, `knowledge/INDEX.md`     | **deleted**               |

`documents.kind` changes its two values from `knowledge` / `inbox` to `notes` /
`docs` in one migration. No load-time shim survives it: the data is corrected in
the database and the compatibility branch is removed in the same change.

## The periodic tidy

`reorg.py` already does the work the user wants — a bounded agentic loop that
consolidates duplicate documents and splits over-long ones — but only fires on
an explicit CLI/REST trigger. It is kept and re-aimed at `notes/`.

Two passes with two triggers collapse into one. `POST /{scope}/organize` and
`POST /{scope}/reorg` named the organizer and the reorg respectively; with the
organizer gone there is one pass, so it keeps one name — `organize` — on both
the route and the CLI, and `/reorg` is removed.

`organizer.py` and `organizer_prompt.py` are deleted. Their job was to drain
`knowledge/inbox/` into topic documents; with one flat lane that gradient no
longer exists.

`NotesTidyTrigger` replaces the old idle-debounced auto-organizer and arms the
pass two ways, because they cover different gaps:

- **On idle.** Each write re-arms one coalescing timer; after a quiet spell the
  scopes that changed are tidied. This is the existing mechanism, re-pointed.
- **On an interval.** A periodic sweep over every scope, modelled on the
  sibling `RetentionWorker` — one catch-up pass at boot, then every few hours,
  exceptions logged without killing the loop. It catches what the idle timer
  structurally cannot: files edited in the user's own editor, a daemon
  restarted before its timer fired, and scopes nothing has written to lately.

Both paths call the same entry point and take the store's write lock, so a
sweep and a just-fired idle timer serialize rather than race. With no internal
model configured the pass no-ops. The detail page also gets a manual **Tidy**
button.

Force: the pass may merge duplicates and rewrite notes into topic documents.
Before any overwrite or merge it moves the prior revision into `.history/`, so
an unattended rewrite is always recoverable.

Each pass writes to Coffer's existing audit log. The per-scope
`consolidation-log.md` is not replaced — one log, and no page has to carry a tab
for it.

## Surfaces

- **MCP: 8 tools → 6.** `search`, `grep`, `read`, `list`, `write`, `delete`.
  `set_handoff` and `resume` retire with the handoff lane.
- **CLI.** `coffer knowledge rules` / `handoff` / `consolidation-log` / `merge`
  are removed. `organize` stays as the manual trigger for the tidy pass.
- **HTTP.** `lane_routes.py` and `merge_routes.py` are removed.

## UI

**List page.** The Scope column goes — the Name column already shows `global`,
a project's absolute path, or a collection's name, so the badge restates what
the row has said. The Entries column becomes Notes. The AI-merge action goes with
`merge`. The New-collection dialog drops the vector-retrieval switch: which index
a scope carries is an implementation detail, not a question to put to the user at
creation time.

**Detail page.** Two tabs, Documents and Notes. One filter box above the tree
that matches filenames as you type — client-side, no button, no request. Server
retrieval stays where it belongs: `coffer__search` for agents, `coffer knowledge
recall` for the CLI.

The header keeps the title, the rename pencil and the project path; **Upload**
and **Tidy** are the two buttons, with Settings / Check sources / Reindex behind
an overflow menu. All six badges go — chunk count, byte size, Grep, Keyword are
internal mechanics, and the entry/document counts are already the tree headers.
The degraded-documents warning survives, shown only when there is one. The
per-lane intro blurb and the count that repeats the tree header go too.

## Deleted

| Module                                                        | LOC   |
| ------------------------------------------------------------- | ----: |
| `organizer.py` + `organizer_prompt.py` (+ deps/ports)         | ~530  |
| `merge.py` + `merge_prompt.py` + `merge_routes.py` + CLI      | ~560  |
| `rules_split.py` + `rules_files.py`                           | ~290  |
| `handoff.py` + `handoff_files.py`                             | ~190  |
| `lane_reads.py` + `lane_deletes.py` + `lane_routes.py`        | ~270  |
| `knowledge_lane_cmd.py` (less the retained `organize`)        |  ~100 |
| **Backend total**                                             | ~1900 |
| Rules / Handoff / Changelog lanes, `KnowledgeListLane`, merge dialog, search bar | ~600 (frontend) |

Against that, one new worker of roughly 60 lines.

`merge` (FR-056…058) is deleted on the maintainer's delegation. The
fragmentation it heals — one repository split across several `project-<ULID>`
scopes — was caused by worktrees hashing to distinct ULIDs, and that root cause
was fixed in the worktree-aware `git_root` change. The residue is healed
automatically at every daemon start by `consolidate.py`. A second, manual path
over the same problem that also drags in LLM judgment and no-resurrection
identity aliases is an abstraction the project no longer pays for.

## Deliberately kept

- **`consolidate.py`.** Despite the name it is not part of the tidy pass: it is
  the one-time startup heal for duplicate per-project scopes. Untouched.
- **Vector retrieval.** Removing the create-dialog switch removes a *question*,
  not the capability. New collections keep keyword + grep + vector; the
  embedding model stays installation-wide.
- **`coffer__search`.** The UI filtering on filenames is a UI decision. Agent-
  facing retrieval is unchanged.

## Accepted risks

The tidy pass runs unattended, on a timer, with an LLM rewriting text the user
and their agents wrote. `.history/` is the whole safety net; there is no
review step and no diff to approve before a pass lands.

## Documentation to update in the same change

- `spec.md` / `spec.zh.md` — drop FR-056…058, the rules-lane FRs and the handoff
  FRs; rewrite the lane layout; add the periodic-tidy FRs.
- `.specify/memory/architecture.md` — the `knowledge` kind row.
- `.specify/memory/roadmap.md` — the 007 row.
- `docs/decisions/Files as Truth`, `One Shared Knowledge Store` — rewritten in place, not superseded by a
  new ADR (repo convention: this directory records the design in force, git
  history is the archive).

---

## Summary

Memory is the **memory face** of one unified knowledge substrate shared with the knowledge base (the Knowledge Base spec). Each memory scope is a Resource of kind `memory`. Facts are per-fact markdown files (YAML frontmatter + body) plus a regenerated `MEMORY.md` index under `~/.coffer/memory/`. **Files are the source of truth; SQLite (`documents` + FTS5 + sqlite-vec) is a rebuildable index.** There are two scopes: global (sentinel ULID) and per-project (project ULID resolved from the agent's working directory).

No LLM runs at write time — the agent writes a clean fact directly. Every agent reads and writes memory **only through Coffer's MCP gateway** (`coffer__recall/remember/list_memory/set_handoff/resume`); Coffer keeps its own canonical format and **does not touch agents' native memory files** (native projection was removed — see [Memory via MCP](../../docs/decisions/memory-via-mcp-not-native-projection.md)). The user does full CRUD through the CLI/REST write surface; the Coffer UI is a **read-only** viewer that offers open-in-editor / reveal for each fact and its folder (curation happens in the user's own editor, picked up by lazy reindex-on-read).

This redesign **drops mem0, chroma, and LlamaIndex** and replaces `memory_records` with the unified `documents` table. There is no data migration (branch unreleased).

## Technical Context

| Dimension                                     | Value                                                                                                                                                                                                                      |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Language / Version**                        | Python 3.12+, TypeScript 5.x                                                                                                                                                                                               |
| **Primary Dependencies (added by this spec)** | Shared with KB: `sqlite-vec` (vector index), `fastembed` (optional local embeddings), `PyYAML` (frontmatter). Cloud embeddings via the existing OpenAI-compatible provider abstraction. **Removed:** `mem0ai`, `chromadb`. |
| **Storage**                                   | Markdown facts under `~/.coffer/memory/global/` and `~/.coffer/memory/projects/<project-ulid>/`; index rows in `~/.coffer/coffer.db` (`documents`, `chunks`, `documents_fts`, `vec_chunks`).                               |
| **Testing**                                   | 4-tier model with acceptance markers. `FakeEmbeddingProvider` for vector paths; keyword/grep need no embeddings.                                                                                                           |
| **Performance Goals**                         | SC-003: ≤ 300 ms keyword recall on a 200-fact scope.                                                                                                                                                                       |
| **Constraints**                               | Index engine confined to `coffer.infrastructure.knowledge.*` (importlinter); daemon starts even if the vector backend fails to load; `mem0`/`chroma`/`llama_index` imported nowhere.                                       |
| **Scale / Scope**                             | Single user; one global store + one store per active project; facts are short (default ≤ 8192 chars).                                                                                                                      |

## Constitution Check

Same layer rules as KB (one substrate). The memory kind reuses the shared retrieval engine, repository, and converters; only the memory-specific service (per-fact write, `MEMORY.md` regeneration, scope resolution) is memory-specific. Engine isolation and the cross-kind import bans extend symmetrically. The `WORKSPACE_GLOBAL_PROJECT_ID` sentinel is reused, not re-minted.

## Project Structure

```text
backend/coffer/
├── domain/
│   ├── errors.py                        # canonical hierarchy: MemoryStoreNotFound, MemoryNotFound, MemoryRejected, ScopeUnresolved, ...
│   ├── knowledge/                       # shared substrate (KB + memory) — see Knowledge Base
│   │   ├── document.py                  # Document entity (kind-discriminated)
│   │   ├── retrieval.py                 # StoreRef, Passage, GrepHit/GrepResult, MemoryHit, SearchResult, RetrievalMode
│   │   ├── index.py                     # KnowledgeIndex / GrepPort / RetrievalPort protocols
│   │   └── errors.py                    # re-exports of the substrate errors (canonical classes in domain/errors.py)
│   └── memory/
│       ├── config.py                    # MemoryStoreConfig (retrieval modes, flat embedding fields, max_fact_chars)
│       ├── fact.py                      # MemoryFact (frontmatter + body) value object
│       └── scope.py                     # MemoryScope (GLOBAL | PROJECT) + ResolvedScope
├── application/
│   ├── knowledge/                       # shared substrate application layer (Knowledge Base)
│   │   ├── retrieval.py                 # KnowledgeRetrieval facade (keyword/vector + flagged fallback)
│   │   ├── reindex.py                   # the single idempotent re-index routine (Reindexer)
│   │   └── locks.py                     # StoreLocks — per-store write serialization
│   ├── memory/
│   │   ├── kind.py                      # make_memory_kind(...)
│   │   ├── service.py / service_helpers.py  # remember/recall/update/forget/list/clear over the knowledge-lane inbox
│   │   ├── writes.py / queries.py       # fact write/read paths
│   │   ├── recall.py                    # recall orchestration + reciprocal-rank-fusion merge
│   │   ├── scope.py                     # ScopeResolver: cwd → git-root → project ULID → store (lazy provision); store-name validation
│   │   ├── stores.py                    # store-name ↔ ResolvedScope helpers
│   │   ├── sync.py                      # MemoryReconciler — lazy reindex-on-read
│   │   └── builtin_tools.py             # the five coffer__* memory MCP tools
├── infrastructure/
│   ├── knowledge/                       # shared substrate infra (Knowledge Base): repository.py, sqlite_index.py,
│   │   …                                # vec_index.py (sole sqlite_vec importer), embeddings.py, grep.py,
│   │                                    # chunking.py, cleaning.py, frontmatter.py, paths.py, converters/
│   └── memory/
│       ├── files.py                     # per-fact .md read/write, MEMORY.md render, dir scan (deltas)
│       ├── paths.py                     # ~/.coffer/memory/{global,projects/<ulid>}
│       ├── scope_fs.py                  # filesystem scope helpers
│       └── project_root_repo.py         # project-root persistence (readable per-project store identity, FR-017a)
└── surfaces/
    ├── http/memory/                     # /api/v1/memory_stores/* (facts, recall)
    └── cli/memory_cmd.py                # `coffer memory ...`
```

Existing files modified:

- `application/mcp/gateway.py` / `gateway_builtin.py` — route the five memory tools (registered by `application/memory/builtin_tools.py`) alongside the KB tools.
- `surfaces/http/app.py` — `_wire_memory_kind(...)`.
- `surfaces/cli/main.py` — `app.add_typer(memory_cmd.app, name="memory")`.
- `infrastructure/persistence/migrations/` — one revision: drop `memory_records`, delete chroma/LlamaIndex dirs, create unified schema.
- `backend/pyproject.toml` — drop `mem0ai`/`chromadb`; add shared substrate deps; new importlinter contract.
- `frontend/src/kinds.ts` — register `MEMORY_KIND_UI`.

## Frontend

```text
frontend/src/pages/MemoryPage.tsx        # stores table (auto-provisioned; no "New store" action)
frontend/src/kinds/memory/
├── index.tsx                            # MEMORY_KIND_UI
├── MemoryStoreDetailPage.tsx            # per-store detail page (route /memory/:name)
├── MemoryFactList.tsx                   # DataTable (name, description, type, actor, updated)
├── MemoryFactViewer.tsx                 # read-only fact render + open-in-editor / reveal (file + folder)
├── MemoryRecallPanel.tsx                # recall box with mode selector (keyword default)
├── MemoryMetricsHeader.tsx              # fact count + disk bytes
├── api.ts / types.ts
└── schema.ts
```

## Tests

```text
backend/tests/
├── unit/memory/
│   ├── test_config_validation.py
│   ├── test_fact_frontmatter_roundtrip.py
│   ├── test_memory_md_regeneration.py        # idempotent, derived from frontmatter
│   └── test_scope_resolver.py                # cwd → git-root → ULID; global sentinel
├── integration/memory/
│   ├── test_remember_recall_roundtrip.py     # keyword + vector(fake) + grep
│   ├── test_lazy_reindex_on_read.py          # out-of-band edit visible on next recall
│   ├── test_two_layer_scope.py               # project + global; cross-project isolation
│   ├── test_mcp_builtin_memory_tools.py
│   ├── test_http_routes.py
│   └── test_cli_memory_cmd.py
└── contract/
    └── test_memory_openapi.py

frontend/src/kinds/memory/
├── FactList.test.tsx
├── FactViewer.test.tsx                       # read-only render + open/reveal affordances
└── RecallBox.test.tsx
```

## Importlinter contracts (added or amended)

- **Extend cross-kind contract**: `coffer.{domain,application,...}.memory` must not import `mcp` or `knowledge_base` and vice versa (the shared `knowledge` substrate is allowed for both KB and memory).
- **New substrate-confinement contract**: `coffer.application.*` and `coffer.domain.*` MUST NOT import the index engine (`sqlite_vec`, FTS5 helpers, embedding SDKs); only `coffer.infrastructure.knowledge.*` may. `mem0`, `chromadb`, and `llama_index` MUST NOT be imported anywhere.

## Risks & mitigations

| Risk                                                                     | Mitigation                                                                                                                                                                                                         |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| MCP shim cwd does not propagate on some agent (scope resolution fails)   | Open item #1 in [research.md](./research.md) (§11); verify on Claude/Codex during impl. An unresolved project scope is REJECTED with `ScopeUnresolved` (clear error; nothing written); `scope=global` still works. |
| A fact file or `MEMORY.md` is edited out of band (e.g. directly on disk) | `MEMORY.md` is a derived index regenerated idempotently; lazy reindex-on-read reconciles fact deltas by content hash — no watcher.                                                                                 |
| sqlite-vec packaging/loading on macOS arm64 / Linux                      | Open item #2 in [research.md](./research.md) (§11); default retrieval is keyword+grep (no native ext needed); vector is opt-in and degrades gracefully when the ext is absent.                                     |
| Embedding model embeds Chinese poorly                                    | Default is keyword+grep (language-agnostic); recommend local `bge-m3` or a cloud provider for bilingual vector recall.                                                                                             |

## Out of scope (deferred)

- Reranking / HyDE / multi-query / LLM synthesis on recall (the agent synthesizes).
- Native projection into agents' own memory surfaces (symlink / managed block); agents access memory only through the MCP tools (native projection was removed — see [Memory via MCP](../../docs/decisions/memory-via-mcp-not-native-projection.md)).
- Multi-machine sync (constitutional).
- Filesystem watcher on by default (memory uses lazy reindex-on-read instead).
- Memory categories beyond `metadata.type` free-form tagging.
