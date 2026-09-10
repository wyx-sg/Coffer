# Data Model — Memory (Shared Agent Memory)

> 中文版: [data-model.zh.md](./data-model.zh.md)

> **Historical — 2026-09-10.** The Knowledge Base and Memory specs merged into
> one **Knowledge Layer** on this date. [`spec.md`](./spec.md) is the
> authority for the merged model — one `knowledge` kind, three scopes, one
> storage root `~/.coffer/knowledge/<scope>/`, eight `coffer__*` tools. This
> document records the design as it stood before that merge; where it says
> "memory face", "`memory` kind", `~/.coffer/memory/`, `/api/v1/memory_stores`
> or `coffer memory …`, read the merged equivalents in `spec.md`. The folder
> name `specs/knowledge/` is likewise historical: it is the spec id every
> inbound link and the acceptance audit key on.

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
| `merged_identities`        | `list[str]`                                | Project ULIDs merged INTO this store (FR-058, amendment 2026-07-10). System-managed (never user-set); a resolve whose identity is listed here — and whose own store is gone — lands on this store. Syncs with the resource. Default `[]`. |

The embedding model is **mutable** — changing it re-embeds the store (files are truth). No immutability lock.

The shape difference vs the Knowledge Base spec is deliberate: the memory spec keeps the embedding fields **flat** so the memory surface stays a thin form, while the knowledge-base spec nests them in an `EmbeddingConfig` object. Since the global-embedding redesign the flat fields are legacy — accepted on the wire for compatibility but ignored; indexing and recall both resolve the **global** embedding config. Likewise the recall response's `fallback` is a **boolean** in the memory spec — recall spans multiple stores, so a single fallback-mode string is ill-defined — whereas the knowledge-base spec's single-store search reports a nullable mode enum (`fallback: "keyword" | null`).

### `MemoryFact` (`domain/memory/fact.py`)

Frozen dataclass; the in-memory view of one per-fact markdown file (frontmatter + body).

| Field               | Type                      | Notes                                                                    |
| ------------------- | ------------------------- | ------------------------------------------------------------------------ |
| `id`                | `str`                     | Document id (ULID); also the basis of the `<fact-slug>.md` name.         |
| `title`             | `str`                     | Frontmatter `title` (short title; legacy `name` key still parsed).       |
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

Agents read and write memory only through the MCP gateway tools (`coffer__recall`/`remember`/`list_memory`); fact edit/delete is a user surface (REST/CLI/external editor), not an MCP tool. Coffer never mutates an agent's native memory files (native projection was removed — see [Memory via MCP](../../docs/decisions/memory-via-mcp-not-native-projection.md)).

### Domain errors (canonical classes in `domain/errors.py`, re-exported via `domain/knowledge/errors.py`)

- `MemoryStoreNotFound` — code `"MEMORY_STORE_NOT_FOUND"` (HTTP 404); raised for a malformed store name (anything other than `global` / `project-<26-char ULID>`).
- `MemoryNotFound` — code `"MEMORY_NOT_FOUND"`.
- `MemoryRejected` — code `"MEMORY_REJECTED"`; reasons: `"empty"`, `"too_long"`.
- `ScopeUnresolved` — code `"SCOPE_UNRESOLVED"`; raised when `scope=project` but cwd is not in a git project.
- `EmbeddingUnavailable` — not an error to the caller: `vector` recall degrades to `keyword` and sets `fallback` in the result (never raised to the user).

## Unified SQLite schema (Alembic — one redesign revision)

The redesign revision **drops** `memory_records` and any chroma/LlamaIndex dirs, then creates the unified `documents`-based schema shared with the KB. There is no data migration.

The schema below is the **same unified schema** created by the KB redesign migration (the Knowledge Base spec owns the migration; this is the memory view of it). The redesign revision **drops** `memory_records` and creates these tables.

```sql
-- Shared across KB (kind='knowledge_base') and memory (kind='memory').
CREATE TABLE documents (
    id             TEXT NOT NULL,               -- ULID (KB + memory), minted at first write
    kind           TEXT NOT NULL,               -- 'knowledge' (one kind since 2026-09-10)
    resource_name  TEXT NOT NULL,               -- scope name: 'global' | 'project-<ULID>' | a named collection
    project_id     TEXT NOT NULL,               -- WORKSPACE_GLOBAL sentinel | project ULID
    path           TEXT NOT NULL,               -- canonical .md path on disk = truth
    title          TEXT NOT NULL,               -- memory: frontmatter `title`
    description    TEXT,                         -- memory: frontmatter `description`
    metadata       TEXT NOT NULL DEFAULT '{}',   -- JSON; memory: {actor, origin_session_id}
    content_sha256 TEXT NOT NULL,               -- for lazy-reindex delta detection
    source_mode    TEXT NOT NULL DEFAULT 'native', -- memory: 'native'
    lane           TEXT NOT NULL DEFAULT 'inbox', -- 'knowledge' (a written entry) | 'inbox' (an ingested document); migration 0052
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

**One store per repo, across git worktrees.** The project ULID is `sha256(git-root path)`. A linked git worktree has its own `.git` *file*, so `git_root` (`infrastructure/memory/scope_fs.py`) follows that pointer's `gitdir`/`commondir` to the **main** repo toplevel — every worktree of a repo (and the main checkout) resolves to one ULID, hence one store. Branch resolution (`git_branch`) stays per-worktree, since handoffs are branch-keyed. Stores fragmented by the earlier path-hash-per-worktree behaviour are healed at daemon startup by a one-time, idempotent, additive consolidation (`application/memory/consolidate.py`): it re-resolves each `project_root`, and any store whose name is no longer the canonical `project-<ULID>` for its root has its lane files merged (name collisions kept as `--from-<ulid>` siblings) into the canonical store and is then retired (resource + `documents` + label + root rows).

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
    │   └── rules/*.md                 # procedural lane: rules.md + per-topic <slug>.md after split (store ROOT; outside recall; read on demand; DOES sync)
    └── projects/<project-ulid>/       # one dir per project
        ├── knowledge/
        │   ├── inbox/<item>.md
        │   ├── <topic>.md
        │   └── INDEX.md
        ├── consolidation-log.md
        ├── superseded/<slug>-<ts>.md
        └── rules/*.md                    # rules.md + per-topic <slug>.md (autonomous split past the threshold)
```

There is **no `MEMORY.md`** — the prior derived projection is removed. `recall` globs `knowledge/**/*.md` (excluding `INDEX.md`), so it transparently picks up topic docs once the organizer writes them and finds a hand-written topic doc immediately. `INDEX.md` and the store-root `consolidation-log.md` are **derived/machine-local**: excluded from recall and from the sync mirror (each machine regenerates `INDEX.md` from the synced topic docs; the log is per-machine). Topic docs themselves are source-of-truth and DO sync. The store-root **`superseded/`** tombstone holds prior versions retired by the reorg pass (FR-033/034): like `handoff/` it sits outside the `knowledge/` lane so it is **excluded from recall**, but unlike the derived files it **DOES sync** — it is recoverable source-of-truth history, not a regenerated artifact. The store-root **`rules/`** lane is the **procedural lane** (FR-036): the organizer classifies rule-shaped inbox items into `rules/rules.md` (append, not topic-merge); once any rules file exceeds the threshold the organizer's reorg pass splits it by topic into per-category `rules/<slug>.md` files (amendment 2026-06-22), and the read surface concatenates every `rules/*.md`. It sits outside the `knowledge/` lane so it is **excluded from recall** (a rule is a standing instruction, not a retrieval hit), and it **DOES sync** as source-of-truth (like `handoff/`). It is read **on demand only** — the session-start injection that once pushed it into an agent is removed (spec FR-049/FR-050/FR-052/FR-055 deleted). It is read-only over `GET /memory_stores/{name}/rules` / `coffer memory rules`. A boot-time reindex sweep (`run_memory_reindex_sweep`) indexes any `knowledge/` lane content that reached disk while its store was not being recalled.

The **organizer** (`application/memory/organizer.py`, internal-LLM, explicit `organize` trigger only) drains `inbox/` into the topic docs via a one-shot completion per item: retrieve up to 3 candidate topic docs (no LLM) → one LLM merge/create call → write `knowledge/<slug>.md` → delete the inbox item (only after the write succeeds) → append a changelog line. A malformed LLM response skips the item (left in inbox, never corrupts a doc). Topic-doc `.md` frontmatter is `{title, description, updated_at}` + body. The langchain LLM call stays in `infrastructure/chat` (Contract 9); `application/memory` reaches it through a memory-local `LlmCompletionPort`.

The **reorg pass** (`application/memory/reorg.py`, internal-LLM, explicit `reorg` trigger only — FR-033/034) deepens the organizer with an **agentic** loop: a bounded langgraph `create_react_agent` (confined to `infrastructure/llm` by Contract 9a, reached via an injected memory-local port) driving four internal tools over the topic docs — `list_topics`, `read_topic`, `write_topic`, `supersede_topic`. It consolidates duplicate/overlapping docs and splits over-long ones. The data-loss guarantee is one invariant: **no byte leaves the `knowledge/` lane without first being archived** — a `write_topic` that overwrites an existing doc archives the prior version to `superseded/<slug>-<ts>.md` before writing, and `supersede_topic` moves the doc there. After the loop the pass regenerates `INDEX.md` and reconciles. The four tools are **internal LangChain `StructuredTool`s** built from memory-local callables — never registered on the MCP gateway, never agent-facing.

Per-fact `.md` frontmatter:

```markdown
---
kind: knowledge
title: deploy-via-make-release
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
| Lane delete (REST)                             | `DELETE /memory_stores/{name}/{handoff/<branch>,rules,consolidation-log}` → remove the lane file(s) (none of these lanes is indexed for recall) → append one human-readable line to `consolidation-log.md` (EXCEPT the changelog's own delete) → audit `memory_deleted`. A missing lane file → 404 (mirrors fact-delete). |
| Clear a scope                                  | Delete every memory item under `knowledge/` → remove all index rows → audit. Store Resource preserved.                                                                        |
| Organize (explicit trigger; internal LLM)      | Per inbox item: retrieve ≤3 candidate topic docs → one-shot LLM merge/create/**classify** → if the LLM marks the item a **rule**, append it to `rules/rules.md` (procedural lane, FR-036); else write `knowledge/<slug>.md` → delete the inbox item (only after the write/append) → append `consolidation-log.md`. Then regenerate `INDEX.md`, reconcile the index, **split any over-threshold `rules/*.md` file into per-topic `rules/<slug>.md` via a one-shot LLM classify** (amendment 2026-06-22). Malformed LLM output skips the item (stays in inbox); no internal model → no-op. |
| Reorg (explicit trigger; internal agentic LLM) | A bounded langgraph `create_react_agent` loop over the topic docs with list/read/write/supersede tools: consolidate duplicates + split over-long docs. **Every overwrite/supersede first archives the prior version to `superseded/<slug>-<ts>.md`** (never hard-delete). Then regenerate `INDEX.md` and reconcile. No internal model → no-op (`no_model`); no topic docs → no-op (`empty`). |
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

| Value              | When emitted                              |
| ------------------ | ----------------------------------------- |
| `"memory_deleted"` | After a successful user delete (REST/CLI) |
| `"memory_cleared"` | After clearing a scope                    |

Only the destructive pair is audited. A write, an edit, an organize, a reorg
and a reindex are all recoverable and all leave their result on disk — the file
IS the record, and re-running any of them changes nothing a reader would need
the log to reconstruct. A delete leaves nothing behind, which is what makes it
worth a row.

### Rules delivery — removed (was slice 6, FR-049/FR-050/FR-052/FR-055)

Slice 6 used to deliver the rules lane into a running agent: Coffer installed a
`coffer-hook` SessionStart hook into the agent's own hooks config, the hook
called `GET /api/v1/agents/{name}/session-context?cwd=<cwd>`, and the daemon
assembled a bundle (project rules, then global rules, then two seeded built-in
rules, then a title-only project-knowledge index) which the hook emitted as
`additionalContext`. A per-agent `disable_native_memory` switch rode alongside
it.

**All of it is gone.** Deleted with the slice: the `coffer-hook` binary and its
PyInstaller spec, `application/agent/hook_service.py`,
`domain/agent/hook_install.py`, `domain/agent/context_injection.py`,
`infrastructure/agent/hook_resolver.py`, the native-memory modules,
`application/knowledge/rules_bundle.py` (the bundle assembler), the digest
renderer, the `GET /api/v1/agents/{name}/session-context` route, the
hook-install trio, and `contracts/session-context.openapi.yaml`. The four audit
event types this slice defined — `agent_hook_installed`,
`agent_hook_uninstalled`, `agent_native_memory_disabled`,
`agent_native_memory_restored` — are removed from `AuditEventType`.

What survives is the read side only. `application/knowledge/session_context.py`
keeps its name but holds only the read helpers — `get_rules(scope)`, every
`rules/*.md` concatenated, plus the post-write `notify_change` hook — behind
`GET /api/v1/knowledge/{scope}/rules` and
`coffer knowledge rules <scope>`. Nothing pushes the lane into a session any
more; an agent that wants it must ask. See the spec's "Delivery — removed" for
why that trade was accepted.

## Lane read endpoints (slice 7 — FR-053/FR-054)

The memory store detail page presents the store as three lane sections
(Knowledge / Rules / Handoff) plus a consolidation-changelog view
(FR-053). Knowledge reuses the existing fact read surface (`GET …/facts`) and is
what `recall` operates over; Rules already has `GET …/{name}/rules` (FR-036).
Slice 7 adds two more **read-only** lane endpoints (FR-054), each addressed by
**store name** (not cwd) — they are thin **read projections of on-disk lane
files**, no LLM, mirroring `get_rules`/metrics on `MemoryService` (resolve
`store_dir` via the resolved scope, read via the lane path helper + infra reader
off the request thread). An empty store returns an **empty list / `null` with
HTTP 200** — never a 404.

| Method + path                                        | Returns               | Lane source                                                                 |
| ---------------------------------------------------- | --------------------- | -------------------------------------------------------------------------- |
| `GET /api/v1/memory_stores/{name}/handoff`           | `HandoffOut`          | `handoff/<branch-slug>.md` scenes, one per branch (continuity; FR-023).     |
| `GET /api/v1/memory_stores/{name}/consolidation-log` | `ConsolidationLogOut` | `consolidation-log.md` at the store root; `text = null` when absent (FR-031). |

### Response entities (read-only projections)

These are **read DTOs only** — not new domain entities or tables. Each surfaces
the lane file's on-disk truth (absolute `.md` `path` + containing `folder_path`)
so the read-only lane views can offer the FR-021 open-in-editor / reveal /
copy-path affordances, exactly like `FactOut`.

**`HandoffSceneOut`** — one per-branch handoff scene.

| Field        | Type            | Notes                                                       |
| ------------ | --------------- | ----------------------------------------------------------- |
| `branch`     | `str`           | Branch the scene belongs to (frontmatter `branch`).         |
| `text`       | `str`           | The scene's freeform markdown body.                         |
| `updated_at` | `str` (date-time) | When the scene was last written (frontmatter `updated_at`). |
| `path`       | `str`           | Absolute on-disk `.md` path of the handoff scene file.      |
| `folder_path`| `str`           | Absolute path of the containing `handoff/` folder.          |

**`HandoffOut`**

| Field    | Type                | Notes                                                       |
| -------- | ------------------- | ----------------------------------------------------------- |
| `scenes` | `HandoffSceneOut[]` | One scene per branch; empty list for a store with no handoff. |

**`ConsolidationLogOut`** — the organizer's append-only consolidation changelog.

| Field         | Type          | Notes                                                            |
| ------------- | ------------- | ---------------------------------------------------------------- |
| `text`        | `str \| None` | The `consolidation-log.md` body; `null` when the file is absent. |
| `path`        | `str`         | Absolute on-disk path of `consolidation-log.md` (store root).    |
| `folder_path` | `str`         | Absolute path of the containing store directory.                 |

These read endpoints (with their schemas) land in the OpenAPI contract owned by
the backend; the spec/data-model side documents only the shapes above.

## Wire contract (REST)

Lives in `contracts/api.openapi.yaml`. Routes under `/api/v1/memory_stores` (list/get/metrics; add/list/get/edit/delete/clear facts; recall; the slice-7 handoff/consolidation-log lane reads of FR-054). The write endpoints (add/edit/delete/clear) are retained — they are how agents (via MCP) and the CLI author facts; the web UI is a read-only viewer. Read DTOs surface on-disk truth: `FactOut` carries the fact's absolute `.md` `path` and its containing folder's `folder_path`, and `MemoryStoreOut` carries the store's absolute `store_dir`, so the read-only viewer can offer open-in-editor / reveal. The kind-agnostic `/api/v1/resources/...` continues to work for memory stores. App-wide error envelope: `{ "error": { "code", "message", "details" } }`.

There is no longer a second, agent-scoped contract: `contracts/session-context.openapi.yaml` is deleted along with the `GET …/session-context` route it described (see "Rules delivery — removed" above).
