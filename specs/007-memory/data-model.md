# Data Model — 007 Memory (Shared Agent Memory)

> 中文版: [data-model.zh.md](./data-model.zh.md)

Entities, ports, the unified SQLite schema (shared with the knowledge base), and the on-disk canonical layout for the memory face.

## Domain entities (`backend/coffer/domain/memory/`)

### `MemoryStoreConfig` (`domain/memory/config.py`)

Pydantic v2 `BaseModel`. Held inside `Resource.config` when `kind == "memory"`. Shares the retrieval-mode vocabulary and embedding semantics with the KB face; the field layout deliberately differs — see below.

| Field                      | Type                                       | Notes                                                                                              |
| -------------------------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| `retrieval_modes`          | `list[Literal["grep","keyword","vector","hybrid"]]` | Enabled modes. Default `["grep","keyword"]` (zero config, offline). `vector` is opt-in; `hybrid` (RRF of keyword+vector) is shared with the KB face.            |
| `default_mode`             | `Literal["grep","keyword","vector","hybrid"]`       | Default `"keyword"`.                                                                               |
| `embedding_provider`       | `str \| None`                              | OpenAI-compatible provider id (e.g. `openai`, `voyage`, `local`). Required for `vector`.           |
| `embedding_model`          | `str \| None`                              | e.g. `bge-m3` (local) or a cloud model. Required for `vector`.                                     |
| `embedding_base_url`       | `str \| None`                              | Override base URL for OpenAI-compatible providers.                                                 |
| `embedding_credential_ref` | `str \| None`                              | Keychain ref for the embedding API key (never plaintext).                                          |
| `embedding_dimensions`     | `int`                                      | Default `768`; range `1–8192`. Drives the per-store `vec_chunks` table width; carried on the wire. |
| `max_fact_chars`           | `int`                                      | Default `8192`; range `64–32768`. Mutable.                                                         |

The embedding model is **mutable** — changing it re-embeds the store (files are truth). No immutability lock.

The shape difference vs spec 006 is deliberate: 007 keeps the embedding fields **flat** so the memory surface stays a thin form, while 006 nests them in an `EmbeddingConfig` object. Since the global-embedding redesign the flat fields are legacy — accepted on the wire for compatibility but ignored; indexing and recall both resolve the **global** embedding config. Likewise the recall response's `fallback` is a **boolean** in 007 — recall spans multiple stores, so a single fallback-mode string is ill-defined — whereas 006's single-store search reports a nullable mode enum (`fallback: "keyword" | null`).

### `MemoryFact` (`domain/memory/fact.py`)

Frozen dataclass; the in-memory view of one per-fact markdown file (frontmatter + body).

| Field               | Type                      | Notes                                                                    |
| ------------------- | ------------------------- | ------------------------------------------------------------------------ |
| `id`                | `str`                     | Document id (ULID); also the basis of the `<fact-slug>.md` name.         |
| `name`              | `str`                     | Frontmatter `name` (short title).                                        |
| `description`       | `str`                     | Frontmatter `description` (one-line).                                    |
| `body`              | `str`                     | Markdown body = the fact text.                                           |
| `actor`             | `Literal["agent","user"]` | Frontmatter `metadata.actor` — who wrote it.                             |
| `origin_session_id` | `str \| None`             | Frontmatter `origin_session_id`.                                         |
| `created_at`        | `datetime`                | UTC.                                                                     |
| `updated_at`        | `datetime`                | UTC (== created_at until edited).                                        |

### `MemoryScope` (`domain/memory/scope.py`)

```python
class MemoryScope(StrEnum):
    GLOBAL = "global"     # project_id = WORKSPACE_GLOBAL_PROJECT_ID
    PROJECT = "project"   # project_id = <project ULID> resolved from cwd

@dataclass(frozen=True)
class ResolvedScope:
    scope: MemoryScope
    project_id: str       # ULID; sentinel for GLOBAL
    store_dir: Path       # ~/.coffer/memory/global | projects/<ulid>
```

### `MemoryHit` (`domain/knowledge/retrieval.py`, shared)

Frozen dataclass; recall result.

| Field    | Type       | Notes                                                        |
| -------- | ---------- | ------------------------------------------------------------ |
| `id`     | `str`      | Fact (document) id.                                          |
| `text`   | `str`      | Fact body / matched passage.                                 |
| `score`  | `float`    | Per-store relevance score (kept on the wire; see RRF below). |
| `source` | `str`      | `<scope>:<fact file path>` of the source fact file.          |
| `time`   | `datetime` | `updated_at` of the fact.                                    |

Cross-store recall merges per-store hit lists by **reciprocal rank fusion** (k=60): raw scores across stores/modes are not comparable (flipped bm25 is unbounded, vector ≤ 1, grep is flat), so RRF ranks by per-store position — each hit keeps its original score, only the merged ORDER comes from the fusion. `grep` recall is served for real: ripgrep over the store's fact files (essential for content FTS5 cannot tokenize, e.g. CJK). Store names are validated (`global` | `project-<26-char ULID>`): a well-formed name lazily provisions its store; anything else 404s.

### Ports

Retrieval is **shared** with the KB face. The value objects (`StoreRef`, `Passage`, `GrepHit`, `GrepResult`, `MemoryHit`, `SearchResult`, `RetrievalMode`) live in `domain/knowledge/retrieval.py`; the protocols (`KnowledgeIndex`, `GrepPort`, `RetrievalPort`) live in `domain/knowledge/index.py`. The concrete facade is `KnowledgeRetrieval` (`application/knowledge/retrieval.py`): it composes the chunk index (`infrastructure/knowledge/sqlite_index.py` + `vec_index.py`), the ripgrep wrapper (`grep.py`), and the embedder clients (`embeddings.py`), and owns the keyword↔vector decision including the flagged vector→keyword fallback — so neither face duplicates it. The lazy reindex-on-read reconcile is the memory-side `MemoryReconciler` (`application/memory/sync.py`) driving the single re-index routine (`application/knowledge/reindex.py`).

Agents read and write memory only through the MCP gateway tools (`coffer__recall`/`remember`/`list_memory`); fact edit/delete is a user surface (REST/CLI/external editor), not an MCP tool. Coffer never mutates an agent's native memory files (native projection was removed — see ADR-026).

### Domain errors (canonical classes in `domain/errors.py`, re-exported via `domain/knowledge/errors.py`)

- `MemoryStoreNotFound` — code `"MEMORY_STORE_NOT_FOUND"` (HTTP 404); raised for a malformed store name (anything other than `global` / `project-<26-char ULID>`).
- `MemoryNotFound` — code `"MEMORY_NOT_FOUND"`.
- `MemoryRejected` — code `"MEMORY_REJECTED"`; reasons: `"empty"`, `"too_long"`.
- `ScopeUnresolved` — code `"SCOPE_UNRESOLVED"`; raised when `scope=project` but cwd is not in a git project.
- `EmbeddingUnavailable` — not an error to the caller: `vector` recall degrades to `keyword` and sets `fallback` in the result (never raised to the user).

## Unified SQLite schema (Alembic — one redesign revision)

The redesign revision **drops** `memory_records` and any chroma/LlamaIndex dirs, then creates the unified `documents`-based schema shared with the KB. There is no data migration.

The schema below is the **same unified schema** created by the KB redesign migration (spec 006 owns the migration; this is the memory view of it). The redesign revision **drops** `memory_records` and creates these tables.

```sql
-- Shared across KB (kind='knowledge_base') and memory (kind='memory').
CREATE TABLE documents (
    id             TEXT NOT NULL,               -- ULID (KB + memory), minted at first write
    kind           TEXT NOT NULL,               -- 'knowledge_base' | 'memory'
    resource_name  TEXT NOT NULL,               -- store name (memory: scope store)
    project_id     TEXT NOT NULL,               -- WORKSPACE_GLOBAL sentinel | project ULID
    path           TEXT NOT NULL,               -- canonical .md path on disk = truth
    title          TEXT NOT NULL,               -- memory: frontmatter `name`
    description    TEXT,                         -- memory: frontmatter `description`
    metadata       TEXT NOT NULL DEFAULT '{}',   -- JSON; memory: {actor, origin_session_id}
    content_sha256 TEXT NOT NULL,               -- for lazy-reindex delta detection
    source_mode    TEXT NOT NULL DEFAULT 'native', -- memory: 'native'
    locked         BOOLEAN NOT NULL DEFAULT 0,  -- KB co-management lock (ADR-028); memory ignores it
    created_at     TIMESTAMP NOT NULL,
    updated_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (kind, resource_name, id)        -- composite (memory ULIDs are globally unique too)
);
CREATE INDEX idx_documents_kind_res_time ON documents(kind, resource_name, updated_at DESC);
CREATE INDEX idx_documents_project ON documents(project_id);

CREATE TABLE chunks (
    id           TEXT PRIMARY KEY,              -- '<store-scope>:<doc-id>:<position>'
    -- store-scope = 12-hex digest of (kind, resource_name); keeps ids unique across stores
    document_id  TEXT NOT NULL,                 -- app-level cascade (not a FK; KB+memory share the table)
    kind         TEXT NOT NULL,
    resource_name TEXT NOT NULL,
    position     INTEGER NOT NULL               -- memory: per-passage chunks (1 for a short inbox fact; N for a multi-section topic doc)
);
CREATE INDEX idx_chunks_document ON chunks(document_id);

-- FTS5 keyword index; the chunk text lives once inside the FTS index (not
-- duplicated into a base table), with chunk_id mapping a hit back to its row.
CREATE VIRTUAL TABLE documents_fts USING fts5(
    text, resource_name UNINDEXED, chunk_id UNINDEXED, tokenize='trigram'  -- CJK-capable (migration 0033)
);

-- sqlite-vec virtual table (only when a vector mode is enabled); created lazily
-- per store at the configured width.
CREATE VIRTUAL TABLE vec_chunks USING vec0(
    chunk_id TEXT PRIMARY KEY,                  -- bare '<doc-id>:<position>' (the table itself is per-store)
    embedding FLOAT[<dim>]
);
```

The cascade on document delete is **application-level** (the index's `delete_chunks` + the repo's `delete_document`/`delete_resource`), not a SQL FK, because the `documents` table is shared by both faces.

`documents.metadata` for the memory face is Pydantic-validated as `{actor, origin_session_id}`. Per the engineering convention, the metadata JSON is built with `model_dump(mode="json")` so `datetime`/`AnyUrl` values serialize for SQLite.

### Store display side-tables

Two tiny `store_name`-keyed side-tables hold **display metadata** for memory stores (not part of the canonical `documents` substrate; they mirror each other):

```sql
CREATE TABLE memory_store_project_roots (
    store_name   TEXT PRIMARY KEY,   -- e.g. 'project-<ULID>'
    project_root TEXT NOT NULL       -- originating git-root, recorded at provisioning (FR-017a)
);
CREATE TABLE memory_store_labels (
    store_name TEXT PRIMARY KEY,     -- e.g. 'project-<ULID>' or 'global'
    label      TEXT NOT NULL         -- user-set display name (FR-017c)
);
```

The `label` takes precedence over the `project_root`-derived basename when rendering a store's readable identity; clearing the label deletes its row, reverting to the FR-017a derivation / fallback. Neither table touches the store's name (`project-<ULID>`) or `project_id`.

## On-disk canonical layout (source of truth)

```
~/.coffer/
└── memory/
    ├── global/                        # project_id = WORKSPACE_GLOBAL_PROJECT_ID (00000000000000000000000000)
    │   ├── knowledge/                 # the semantic lane (recall searches here)
    │   │   ├── inbox/<item>.md        # per-item file = truth (frontmatter + body), freshly remembered
    │   │   ├── <topic>.md             # organized topic docs (written by the consolidation organizer)
    │   │   └── INDEX.md               # human review entry point (regenerated by the organizer)
    │   ├── consolidation-log.md       # append-only changelog (store ROOT; machine-local, outside recall)
    │   ├── superseded/<slug>-<ts>.md  # reorg tombstone (store ROOT; outside recall; recoverable; DOES sync)
    │   └── rules/rules.md             # procedural lane (store ROOT; outside recall; injected at session start; DOES sync)
    └── projects/<project-ulid>/       # one dir per project
        ├── knowledge/
        │   ├── inbox/<item>.md
        │   ├── <topic>.md
        │   └── INDEX.md
        ├── consolidation-log.md
        ├── superseded/<slug>-<ts>.md
        ├── rules/rules.md
        └── journal/     <YYYY-MM>.md     # episodic, append-only, time-partitioned; synced AND indexed for recall (FR-043)
```

There is **no `MEMORY.md`** — the prior derived projection is removed. `recall` globs `knowledge/**/*.md` (excluding `INDEX.md`), so it transparently picks up topic docs once the organizer writes them and finds a hand-written topic doc immediately. `INDEX.md` and the store-root `consolidation-log.md` are **derived/machine-local**: excluded from recall and from the sync mirror (each machine regenerates `INDEX.md` from the synced topic docs; the log is per-machine). Topic docs themselves are source-of-truth and DO sync. The store-root **`superseded/`** tombstone holds prior versions retired by the reorg pass (FR-033/034): like `handoff/` it sits outside the `knowledge/` lane so it is **excluded from recall**, but unlike the derived files it **DOES sync** — it is recoverable source-of-truth history, not a regenerated artifact. The store-root **`rules/rules.md`** is the **procedural lane** (FR-036): the organizer classifies rule-shaped inbox items into it (append, not topic-merge); it sits outside the `knowledge/` lane so it is **excluded from recall** (rules are delivered by session-start injection, a later slice, not by `recall`), and it **DOES sync** as source-of-truth (like `handoff/`). It is read-only over `GET /memory_stores/{name}/rules` / `coffer memory rules`. The store-root **`journal/`** lane is the **episodic lane** (FR-040): unlike `rules/`/`handoff/`/`superseded/` it **participates in recall** — the reconciler indexes each `journal/<YYYY-MM>.md` as one memory document (chunked like topic docs) and the grep guard keeps `journal/` hits, so episodic events are searchable (FR-043). It still **DOES sync** as source-of-truth history and is **not** counted in a store's `fact_count` (that counts only the `knowledge/` lane).

The **organizer** (`application/memory/organizer.py`, internal-LLM, explicit `organize` trigger only) drains `inbox/` into the topic docs via a one-shot completion per item: retrieve up to 3 candidate topic docs (no LLM) → one LLM merge/create call → write `knowledge/<slug>.md` → delete the inbox item (only after the write succeeds) → append a changelog line. A malformed LLM response skips the item (left in inbox, never corrupts a doc). Topic-doc `.md` frontmatter is `{title, description, updated_at}` + body. The langchain LLM call stays in `infrastructure/chat` (Contract 9); `application/memory` reaches it through a memory-local `LlmCompletionPort` (clone of the distill slice; Contract 5e forbids importing `application.distill`).

The **reorg pass** (`application/memory/reorg.py`, internal-LLM, explicit `reorg` trigger only — FR-033/034) deepens the organizer with an **agentic** loop: a bounded langgraph `create_react_agent` (confined to `infrastructure/chat` by Contract 9, reached via an injected memory-local port — clone of the agentic-RAG slice) driving four internal tools over the topic docs — `list_topics`, `read_topic`, `write_topic`, `supersede_topic`. It consolidates duplicate/overlapping docs and splits over-long ones. The data-loss guarantee is one invariant: **no byte leaves the `knowledge/` lane without first being archived** — a `write_topic` that overwrites an existing doc archives the prior version to `superseded/<slug>-<ts>.md` before writing, and `supersede_topic` moves the doc there. After the loop the pass regenerates `INDEX.md`, reconciles, and audits `memory_reorganized`. The four tools are **internal LangChain `StructuredTool`s** built from memory-local callables — never registered on the MCP gateway, never agent-facing.

Per-fact `.md` frontmatter:

```markdown
---
name: deploy-via-make-release
description: This repo deploys via `make release`, never git push --tags directly.
metadata:
  actor: agent
origin_session_id: 01J...
created_at: 2026-06-09T10:11:12+00:00
updated_at: 2026-06-09T10:11:12+00:00
---

This repo deploys via `make release`. Never run `git push --tags` directly; the
release target tags and pushes atomically.
```

`created_at` / `updated_at` are persisted in the frontmatter (the file is the source of truth); the file mtime is only a fallback when parsing hand-written fact files that omit them.

`infrastructure/memory/paths.py` is the only module that constructs these paths. `infrastructure/memory/files.py` is the only module that reads/writes the per-item `.md` files and scans the `knowledge/` lane for deltas.

## Cascade & integrity rules

| Action                                                | Effect                                                                                                                                                                                      |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `remember` / user add                          | Write `knowledge/inbox/<item-slug>.md` → index into `documents`/`chunks`/FTS5/(vec) → audit.                                                                                  |
| User edit (REST/CLI/external editor)           | Rewrite `.md` → single re-index routine (sha256 changed → re-chunk/-embed) → audit. (A direct external-editor edit takes effect on the next lazy reindex-on-read.) MCP has no edit tool — REST/CLI only. |
| User delete (REST/CLI)                         | Delete `.md` → remove `documents`/`chunks`/FTS5/vec rows → audit. MCP has no delete tool — REST/CLI only.                                                                      |
| Clear a scope                                  | Delete every memory item under `knowledge/` → remove all index rows → audit. Store Resource preserved.                                                                        |
| Organize (explicit trigger; internal LLM)      | Per inbox item: retrieve ≤3 candidate topic docs → one-shot LLM merge/create/**classify** → if the LLM marks the item a **rule**, append it to `rules/rules.md` (procedural lane, FR-036); else write `knowledge/<slug>.md` → delete the inbox item (only after the write/append) → append `consolidation-log.md`. Then regenerate `INDEX.md`, reconcile the index, audit `memory_organized` (with a `rules_appended` count). Malformed LLM output skips the item (stays in inbox); no internal model → no-op. |
| Reorg (explicit trigger; internal agentic LLM) | A bounded langgraph `create_react_agent` loop over the topic docs with list/read/write/supersede tools: consolidate duplicates + split over-long docs. **Every overwrite/supersede first archives the prior version to `superseded/<slug>-<ts>.md`** (never hard-delete). Then regenerate `INDEX.md`, reconcile, audit `memory_reorganized`. No internal model → no-op (`no_model`); no topic docs → no-op (`empty`). |
| Auto-organize (idle trigger; opt-in, default OFF) | The memory write-notify hook (re)arms a single **debounced** timer; after the store is idle for the delay it runs `Organize` (above) for the changed store(s) as a **background task** — a session-end proxy (FR-035). Non-blocking: cancelled on daemon shutdown (the un-fired inbox is left intact for a later pass; no data loss). Failure suppressed + logged. No new REST/CLI surface. |
| Delete the store Resource                      | Remove `documents` rows for the store, `rmtree(store_dir)`, audit.                                                                                                            |
| Recall                                         | **Lazy reindex-on-read**: scan the `knowledge/` lane for deltas (by `content_sha256`) → `reconcile` → search.                                                                 |
| Change embedding model                                | Allowed → re-embed the store on next index (files are truth).                                                                                                                               |
| Change `max_fact_chars`                               | Allowed.                                                                                                                                                                                    |

## The single re-index routine (`application/knowledge/reindex.py`, shared with KB)

```
compute content_sha256 of the new markdown
 ├ unchanged → skip (no-op)
 └ changed   → delete old chunks/FTS5/vec rows → re-chunk → (vector) re-embed
              → insert new → update documents row → audit *_UPDATED
```

All memory write paths (remember, update, user edit, lazy reindex scan) funnel through this one routine.

The memory reconciler supplies its own **chunker** to the routine (per FR-032): the shared `infrastructure/knowledge/chunking.chunk_markdown`, bound to fixed memory chunk-size/overlap constants (not a per-store config), so an organized topic document is split into **per-passage chunks** (heading- and block-structure aware) and `recall` returns its most relevant passage. A short single-passage fact still yields one chunk, so the inbox-vs-topic and `INDEX.md`/`handoff/` recall isolation is unaffected.

When a vector-enabled store's embed degrades (embedding provider unavailable), the routine indexes keyword-only and persists an **empty-string `content_sha256`** — a deliberate never-matching sentinel so the next lazy reconcile retries the embed instead of treating the fact as up to date.

## Audit events added

| Value              | When emitted                            |
| ------------------ | --------------------------------------- |
| `"memory_added"`   | After a successful `remember`/user add  |
| `"memory_updated"` | After a successful user edit (REST/CLI) |
| `"memory_deleted"` | After a successful user delete (REST/CLI) |
| `"memory_cleared"` | After clearing a scope                  |

## Transcript distillation (Spec 007 extension)

Transcript distillation is a **producer of memory facts** — it uses the existing `MemoryFact` substrate (no new tables, no new resource kind).

### Insights are untyped (no classification)

The one-shot LLM call returns a JSON array of insights, each carrying only `name` / `description` / `body` — distillation stays "dumb" and MUST NOT classify a per-insight `type` (the legacy `InsightType` vocabulary `decision` / `gotcha` / `convention` / `todo` is retired — FR-045). Each insight is appended to the session's project **journal** lane (episodic) with `actor="agent"`, never a typed `knowledge/` fact; promotion of recurring journal patterns into `knowledge`/`rules` is the organizer's job (固化 — FR-047). `Lane` is the single classification axis (FR-048); there is no free-form `type`.

### Provenance — `origin_session_id`

Every distilled fact carries `origin_session_id` (the transcript's session id) in the fact frontmatter and in `documents.metadata`. This makes the automated origin auditable: a user can see which session produced a given fact and, if needed, delete or correct it.

Example fact frontmatter for a distilled insight:

```markdown
---
name: use-make-release-for-tagging
description: Always tag and push via make release; never git push --tags directly.
metadata:
  actor: agent
origin_session_id: 01JXYZ…
created_at: 2026-06-14T08:00:00+00:00
updated_at: 2026-06-14T08:00:00+00:00
---

Always tag and push via `make release`. The Makefile target is atomic — it
tags and pushes in one step. Running `git push --tags` directly bypasses the
release checks and can leave the repo in a half-tagged state.
```

### Scrub-before-LLM invariant

The raw transcript is **never persisted** and never reaches the fact body. Before the LLM call:

- All `tool_use` / `tool_result` blocks (Claude/Codex) and non-`text` parts — tool, reasoning, file, step (OpenCode) — are dropped.
- File-content passages and command output embedded in assistant turns are dropped.
- Common secret patterns (API keys, tokens, PEM blocks) are redacted by a regex scrubber.
- Long blobs are truncated.

Only scrubbed natural-language text (user + assistant prose) is sent to the LLM. Only the distilled insight text is written to the fact store. Neither the raw transcript nor the scrubbed intermediate text is stored anywhere in `~/.coffer/`.

Coffer reads `~/.claude/projects/`, `~/.codex/sessions/`, and OpenCode's storage tree (`~/.local/share/opencode/storage/`) but **never writes to them** in this flow — Spec 004's read-only invariant is fully preserved. Readers for Cursor / OpenClaw / Hermes transcripts are deferred (see spec.md, US "distill transcript to memory"): their stores are ephemeral, undocumented, or carry no working directory to scope facts by.

### Audit

Distillation reuses the existing memory write path: the `memory_added` event fires
for each individual fact written, carrying its `origin_session_id`. No
distillation-specific audit event is emitted.

### Transcript session summary (history list view)

The transcript **history** surface lists an agent's past sessions for browsing
and distillation. A summary is a read-only projection parsed from each session
`.jsonl` — nothing is persisted (Spec 004 read-only invariant):

| Field              | Source                                                                                                              |
| ------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `session_id`       | Claude Code `sessionId` / Codex `payload.id`; falls back to the file path.                                          |
| `title`            | Claude Code `ai-title` (latest wins), else the first *real* user message (preambles/shell/slash-commands skipped), truncated; nullable. |
| `project_path`     | Claude Code top-level `cwd` / Codex `session_meta.payload.cwd`.                                                     |
| `message_count`    | Count of conversation turns — Codex counts `response_item` messages only (never the duplicate `event_msg` events). |
| `started_at`       | First event timestamp.                                                                                              |
| `last_activity_at` | Last event timestamp.                                                                                               |
| `source_path`      | Absolute path of the session `.jsonl` (powers reveal-in-file-manager via the shared `FileActions`).                |

The list endpoint applies server-side search (title or project path), filtering
(exact project; `started_at` range), and sorting (`started_at` /
`last_activity_at` / `message_count`, asc/desc), paged by `limit`/`offset`. The
reader keeps an in-process, mtime-keyed cache of parsed summaries, so an agent
with thousands of sessions re-parses only files whose mtime changed.

## Wire contract (REST)

Lives in `contracts/api.openapi.yaml`. Routes under `/api/v1/memory_stores` (list/get/metrics; add/list/get/edit/delete/clear facts; recall). The write endpoints (add/edit/delete/clear) are retained — they are how agents (via MCP) and the CLI author facts; the desktop/web UI is a read-only viewer. Read DTOs surface on-disk truth: `FactOut` carries the fact's absolute `.md` `path` and its containing folder's `folder_path`, and `MemoryStoreOut` carries the store's absolute `store_dir`, so the read-only viewer can offer open-in-editor / reveal. The kind-agnostic `/api/v1/resources/...` continues to work for memory stores. App-wide error envelope: `{ "error": { "code", "message", "details" } }`.
