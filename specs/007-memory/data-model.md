# Data Model — 007 Memory (Shared Agent Memory)

> 中文版: [data-model.zh.md](./data-model.zh.md)

Entities, ports, the unified SQLite schema (shared with the knowledge base), and the on-disk canonical layout for the memory face.

## Domain entities (`backend/coffer/domain/memory/`)

### `MemoryStoreConfig` (`domain/memory/config.py`)

Pydantic v2 `BaseModel`. Held inside `Resource.config` when `kind == "memory"`. Shares the retrieval-mode vocabulary and embedding semantics with the KB face; the field layout deliberately differs — see below.

| Field                      | Type                                       | Notes                                                                                              |
| -------------------------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| `retrieval_modes`          | `list[Literal["grep","keyword","vector"]]` | Enabled modes. Default `["grep","keyword"]` (zero config, offline). `vector` is opt-in.            |
| `default_mode`             | `Literal["grep","keyword","vector"]`       | Default `"keyword"`.                                                                               |
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
| `name`              | `str`                     | Frontmatter `name` (short title; appears in `MEMORY.md`).                |
| `description`       | `str`                     | Frontmatter `description` (one-line; appears in `MEMORY.md`).            |
| `body`              | `str`                     | Markdown body = the fact text.                                           |
| `type`              | `str \| None`             | Frontmatter `metadata.type` (`project`/`feedback`/`reference`/`user`/…). |
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

Agents read and write memory only through the MCP gateway tools (`coffer__recall`/`remember`/`update_memory`/`forget`/`list_memory`); Coffer never mutates an agent's native memory files (native projection was removed — see ADR-026).

### Domain errors (canonical classes in `domain/errors.py`, re-exported via `domain/knowledge/errors.py`)

- `MemoryStoreNotFound` — code `"MEMORY_STORE_NOT_FOUND"` (HTTP 404); raised for a malformed store name (anything other than `global` / `project-<26-char ULID>`).
- `MemoryNotFound` — code `"MEMORY_NOT_FOUND"`.
- `MemoryRejected` — code `"MEMORY_REJECTED"`; reasons: `"empty"`, `"too_long"`.
- `ScopeUnresolved` — code `"SCOPE_UNRESOLVED"`; raised when `scope=project` but cwd is not in a git project.
- `EmbeddingUnavailable` — not an error to the caller: `vector` recall degrades to `keyword` and sets `fallback` in the result (never raised to the user).

## Unified SQLite schema (Alembic — one redesign revision)

The redesign revision **drops** `memory_records` and any chroma/LlamaIndex dirs, then creates the unified `documents`-based schema shared with the KB. There is no data migration.

The schema below is the **same unified schema** created by the KB redesign migration (spec 006 owns the migration; this is the memory view of it). The redesign revision **drops** `memory_records` and creates these tables. Two later additive migrations extend the shared `documents` table — `0025` (`locked`, ADR-028) and `0026` (`deleted_at`, ADR-030); the memory face uses **neither** column (it never locks a fact and `forget` is a hard delete, so `deleted_at` is always NULL for memory rows).

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
    metadata       TEXT NOT NULL DEFAULT '{}',   -- JSON; memory: {type, actor, origin_session_id}
    content_sha256 TEXT NOT NULL,               -- for lazy-reindex delta detection
    source_mode    TEXT NOT NULL DEFAULT 'native', -- memory: 'native'
    locked         BOOLEAN NOT NULL DEFAULT 0,  -- KB co-management lock (ADR-028); memory ignores it
    deleted_at     TIMESTAMP,                   -- KB soft-delete/trash (ADR-030); memory never sets it (forget is hard)
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
    position     INTEGER NOT NULL               -- memory: one chunk per fact
);
CREATE INDEX idx_chunks_document ON chunks(document_id);

-- FTS5 keyword index; the chunk text lives once inside the FTS index (not
-- duplicated into a base table), with chunk_id mapping a hit back to its row.
CREATE VIRTUAL TABLE documents_fts USING fts5(
    text, resource_name UNINDEXED, chunk_id UNINDEXED, tokenize='unicode61'
);

-- sqlite-vec virtual table (only when a vector mode is enabled); created lazily
-- per store at the configured width.
CREATE VIRTUAL TABLE vec_chunks USING vec0(
    chunk_id TEXT PRIMARY KEY,                  -- bare '<doc-id>:<position>' (the table itself is per-store)
    embedding FLOAT[<dim>]
);
```

The cascade on document delete is **application-level** (the index's `delete_chunks` + the repo's `delete_document`/`delete_resource`), not a SQL FK, because the `documents` table is shared by both faces.

`documents.metadata` for the memory face is Pydantic-validated as `{type, actor, origin_session_id}`. Per the engineering convention, the metadata JSON is built with `model_dump(mode="json")` so `datetime`/`AnyUrl` values serialize for SQLite.

## On-disk canonical layout (source of truth)

```
~/.coffer/
└── memory/
    ├── global/                        # project_id = WORKSPACE_GLOBAL_PROJECT_ID (00000000000000000000000000)
    │   ├── MEMORY.md                  # regenerated index: - [name](file.md) — description
    │   └── <fact-slug>.md             # per-fact file = truth (frontmatter + body)
    └── projects/<project-ulid>/       # one dir per project
        ├── MEMORY.md
        └── <fact-slug>.md
```

Per-fact `.md` frontmatter:

```markdown
---
name: deploy-via-make-release
description: This repo deploys via `make release`, never git push --tags directly.
metadata:
  type: project
  actor: agent
origin_session_id: 01J...
created_at: 2026-06-09T10:11:12+00:00
updated_at: 2026-06-09T10:11:12+00:00
---

This repo deploys via `make release`. Never run `git push --tags` directly; the
release target tags and pushes atomically.
```

`created_at` / `updated_at` are persisted in the frontmatter (the file is the source of truth); the file mtime is only a fallback when parsing hand-written fact files that omit them.

`infrastructure/memory/paths.py` is the only module that constructs these paths. `infrastructure/memory/files.py` is the only module that reads/writes the per-fact `.md` files, renders `MEMORY.md`, and scans the dir for deltas.

## Cascade & integrity rules

| Action                                                | Effect                                                                                                                                                                                      |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `remember` / user add                                 | Write `<fact-slug>.md` → regenerate `MEMORY.md` → index into `documents`/`chunks`/FTS5/(vec) → audit.                                                                                       |
| `update_memory` / user edit (API/CLI/external editor) | Rewrite `.md` → single re-index routine (sha256 changed → re-chunk/-embed) → regenerate `MEMORY.md` → audit. (A direct external-editor edit takes effect on the next lazy reindex-on-read.) |
| `forget` / user delete                                | Delete `.md` → remove `documents`/`chunks`/FTS5/vec rows → regenerate `MEMORY.md` → audit.                                                                                                  |
| Clear a scope                                         | Delete all `.md` for the store → remove all index rows → empty `MEMORY.md` → audit. Store Resource preserved.                                                                               |
| Delete the store Resource                             | Remove `documents` rows for the store, `rmtree(store_dir)`, audit.                                                                                                                          |
| Recall                                                | **Lazy reindex-on-read**: scan `store_dir` for deltas (by `content_sha256`) → `reconcile` → search. No write to `MEMORY.md`.                                                                |
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

When a vector-enabled store's embed degrades (embedding provider unavailable), the routine indexes keyword-only and persists an **empty-string `content_sha256`** — a deliberate never-matching sentinel so the next lazy reconcile retries the embed instead of treating the fact as up to date.

## Audit events added

| Value              | When emitted                            |
| ------------------ | --------------------------------------- |
| `"memory_added"`   | After a successful `remember`/user add  |
| `"memory_updated"` | After a successful `update`/user edit   |
| `"memory_deleted"` | After a successful `forget`/user delete |
| `"memory_cleared"` | After clearing a scope                  |

## Transcript distillation (Spec 007 extension)

Transcript distillation is a **producer of memory facts** — it uses the existing `MemoryFact` substrate (no new tables, no new resource kind).

### Insight types

The one-shot LLM call returns a JSON array of insights, each with a `type` drawn from a closed vocabulary:

| `type`       | Meaning                                                                          |
| ------------ | -------------------------------------------------------------------------------- |
| `decision`   | A deliberate architectural or implementation choice made during the session.     |
| `gotcha`     | A non-obvious failure mode, trap, or constraint discovered during the session.   |
| `convention` | A project-specific practice or style rule that should be followed going forward. |
| `todo`       | An explicit action item or open question that was not resolved in the session.   |

Each insight becomes a `MemoryFact` with `actor="agent"` (written by automated distillation, not by a human) and the `type` stored in `metadata.type`.

### Provenance — `origin_session_id`

Every distilled fact carries `origin_session_id` (the transcript's session id) in the fact frontmatter and in `documents.metadata`. This makes the automated origin auditable: a user can see which session produced a given fact and, if needed, delete or correct it.

Example fact frontmatter for a distilled insight:

```markdown
---
name: use-make-release-for-tagging
description: Always tag and push via make release; never git push --tags directly.
metadata:
  type: decision
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

## Wire contract (REST)

Lives in `contracts/api.openapi.yaml`. Routes under `/api/v1/memory_stores` (list/get/metrics; add/list/get/edit/delete/clear facts; recall). The write endpoints (add/edit/delete/clear) are retained — they are how agents (via MCP) and the CLI author facts; the desktop/web UI is a read-only viewer. Read DTOs surface on-disk truth: `FactOut` carries the fact's absolute `.md` `path` and its containing folder's `folder_path`, and `MemoryStoreOut` carries the store's absolute `store_dir`, so the read-only viewer can offer open-in-editor / reveal / copy-path. The kind-agnostic `/api/v1/resources/...` continues to work for memory stores. App-wide error envelope: `{ "error": { "code", "message", "details" } }`.
