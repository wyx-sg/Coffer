# Data Model — 007 Memory (Shared Agent Memory)

> 中文版: [data-model.zh.md](./data-model.zh.md)

> **Historical — 2026-09-10.** Spec knowledge (Knowledge Base) and spec knowledge (Memory)
> merged into one **Knowledge Layer** on this date. [`spec.md`](./spec.md) is the
> authority for the merged model — one `knowledge` kind, three scopes, one
> storage root `~/.coffer/knowledge/<scope>/`, six `coffer__*` tools. This
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

`merged_identities` is gone with the cross-scope AI merge (FR-056…059): it existed
only so a merged-away project ULID kept resolving to the survivor, and nothing
mints those aliases any more.

The embedding model is **mutable** — changing it re-embeds the store (files are truth). No immutability lock.

The shape difference vs spec knowledge is deliberate: 007 keeps the embedding fields **flat** so the memory surface stays a thin form, while 006 nests them in an `EmbeddingConfig` object. Since the global-embedding redesign the flat fields are legacy — accepted on the wire for compatibility but ignored; indexing and recall both resolve the **global** embedding config (`GlobalEmbeddingConfig`, below). Likewise the recall response's `fallback` is a **boolean** in 007 — recall spans multiple stores, so a single fallback-mode string is ill-defined — whereas 006's single-store search reports a nullable mode enum (`fallback: "keyword" | null`).

### `GlobalEmbeddingConfig` (`domain/embedding_config.py`, table `embedding_config`)

The installation-wide embedding settings — a singleton row. It **names a
connection** instead of restating a provider (FR-077): the protocol, base URL and
credential live on the `provider` resource and are resolved from it at use time,
which is the same "pick a provider, then pick a model" shape the internal-engine
setting already uses.

| Field                  | Type          | Notes                                                                                                      |
| ---------------------- | ------------- | ---------------------------------------------------------------------------------------------------------- |
| `enabled`              | `bool`        | Whether installation-wide embedding is on at all.                                                           |
| `connection`           | `str \| None` | NAME of a configured LLM connection (a `provider` resource). Empty ⇒ the config is inactive.                |
| `model`                | `str \| None` | The embedding model id on that connection. Must match one of its curated `embedding` models when it curates any. |
| `dimensions`           | `int`         | Vector width; drives the `vec_chunks` table.                                                                |
| `default_chunk_size`   | `int`         | Default chunk size for a scope that does not override it.                                                   |
| `default_chunk_overlap`| `int`         | Default chunk overlap.                                                                                      |
| `updated_at`           | `datetime`    | Last write.                                                                                                 |

`provider` (the old protocol-name enum), `base_url` and `credential_ref` are
**gone** from the row and from the wire, and the update request carries no
`secret_value`: the key belongs to the connection, and the embedding settings no
longer mint an `embedding/key` vault entry.

`is_active()` is `enabled and connection and model`. A config naming no
connection is inactive, so retrieval degrades to keyword/grep exactly as on an
unconfigured install.

Resolution maps the connection's `protocol` to the embedding client — `openai` →
openai-compatible, `ollama` → ollama, `unknown` → treated as openai-compatible
(that is what an unclassified gateway almost always is); `anthropic` serves no
embedding API and is refused. The connection's `base_url` and `credential_ref`
are used verbatim.

Selection is refused with **HTTP 422** (`CONFIG_INVALID`, the status every other
config rejection in the app returns) when it names a connection that does not
exist, one whose protocol serves no embeddings, one that curates models but none
with modality `embedding`, or a model nothing the connection curates matches. A
connection curating no models at all is accepted (empty = unrestricted) and the
typed model id taken at its word.

**Migration:** one Alembic revision rewrites the singleton row — an existing
config is mapped onto the connection whose `base_url` (or, failing that,
`credential_ref`) matches what it had recorded; when nothing matches, the row
keeps its dimensions and chunk defaults but is left with no connection and
`enabled = 0` rather than inventing a connection. One-shot: the old columns are
dropped in the same revision and no load-time shim reads them.

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

Agents read and write memory only through the MCP gateway's six tools — `coffer__search`, `coffer__grep`, `coffer__read`, `coffer__list`, `coffer__write`, `coffer__delete` (FR-015). `coffer__set_handoff` and `coffer__resume` retired with the handoff lane. Coffer never mutates an agent's native memory files (native projection was removed — see Memory via MCP).

### Domain errors (canonical classes in `domain/errors.py`, re-exported via `domain/knowledge/errors.py`)

- `MemoryStoreNotFound` — code `"MEMORY_STORE_NOT_FOUND"` (HTTP 404); raised for a malformed store name (anything other than `global` / `project-<26-char ULID>`).
- `MemoryNotFound` — code `"MEMORY_NOT_FOUND"`.
- `MemoryRejected` — code `"MEMORY_REJECTED"`; reasons: `"empty"`, `"too_long"`.
- `ScopeUnresolved` — code `"SCOPE_UNRESOLVED"`; raised when `scope=project` but cwd is not in a git project.
- `EmbeddingUnavailable` — not an error to the caller: `vector` recall degrades to `keyword` and sets `fallback` in the result (never raised to the user).

## Unified SQLite schema (Alembic — one redesign revision)

The redesign revision **drops** `memory_records` and any chroma/LlamaIndex dirs, then creates the unified `documents`-based schema shared with the KB. There is no data migration.

The schema below is the **same unified schema** created by the KB redesign migration (spec knowledge owns the migration; this is the memory view of it). The redesign revision **drops** `memory_records` and creates these tables.

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
    lane           TEXT NOT NULL DEFAULT 'docs', -- 'notes' (what someone wrote) | 'docs' (an uploaded document); added by migration 0053; values renamed to notes/docs by 0056 (FR-073/FR-076)
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
    position     INTEGER NOT NULL               -- memory: per-passage chunks (1 for a short note; N for a multi-section topic doc)
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

### The two-lane migration (FR-076)

One Alembic revision (`0056`) renames the discriminator's two values in place —
a value rename, not a schema change, so it is two `UPDATE`s rather than a table
rebuild, and the column's server default moves with them:

| `documents.lane` before | after   |
| ----------------------- | ------- |
| `knowledge`             | `notes` |
| `inbox`                 | `docs`  |

The retired lanes (`rules/`, `handoff/`, `superseded/`, the consolidation log and
`knowledge/INDEX.md`) leave no rows to sweep — none of them was ever indexed for
recall. Their files go in the on-disk half of the migration: a one-time,
idempotent, best-effort sweep at daemon start, modelled on the sibling
worktree-scope consolidation, that moves the two content lanes and deletes the
rest.

The two halves are deliberately independent. Right after the revision a row's
`path` still names the OLD directory, and that is harmless: the lazy
reindex-on-read that follows the filesystem sweep re-derives every path from the
files actually on disk. Anchoring the revision on the stored path instead would
couple it to whether the daemon happened to reach the filesystem pass first.

**No load-time compatibility shim survives.** The old lane strings are corrected
in the database and every branch that read them is deleted in the same change:
nothing in the running system maps `knowledge`→`notes` or `inbox`→`docs` at read
time, and a database that skipped the migration is simply a database the code no
longer understands.

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

**One store per repo, across git worktrees.** The project ULID is `sha256(git-root path)`. A linked git worktree has its own `.git` *file*, so `git_root` (`infrastructure/memory/scope_fs.py`) follows that pointer's `gitdir`/`commondir` to the **main** repo toplevel — every worktree of a repo (and the main checkout) resolves to one ULID, hence one store. Stores fragmented by the earlier path-hash-per-worktree behaviour are healed at daemon startup by a one-time, idempotent, additive consolidation (`application/memory/consolidate.py`): it re-resolves each `project_root`, and any store whose name is no longer the canonical `project-<ULID>` for its root has its lane files merged (name collisions kept as `--from-<ulid>` siblings) into the canonical store and is then retired (resource + `documents` + label + root rows).

## On-disk canonical layout (source of truth)

```
~/.coffer/
└── memory/
    ├── global/                          # project_id = WORKSPACE_GLOBAL_PROJECT_ID (00000000000000000000000000)
    │   ├── notes/                       # what an agent or the user wrote (coffer__write lands here)
    │   │   ├── <note>.md                # per-note file = truth (frontmatter + body)
    │   │   └── .history/<slug>-<ts>.md  # pre-rewrite copies kept by the tidy pass (hidden)
    │   ├── docs/<document>.md           # uploaded documents, normalized to markdown
    │   └── .raw/<document>.<ext>        # the uploaded originals (hidden)
    └── projects/<project-ulid>/         # one dir per project
        ├── notes/
        │   ├── <note>.md
        │   └── .history/<slug>-<ts>.md
        ├── docs/<document>.md
        └── .raw/<document>.<ext>
```

**Two lanes** (FR-002a/FR-048): `notes/` is everything a writer produced — an
agent's `coffer__write`, a `coffer knowledge remember`, a file the user dropped
in with their own editor — and `docs/` is everything that was uploaded,
normalized to markdown. A note is a note whether it was just written or has been
tidied since; there is no inbox-to-topic-document gradient any more, and the two
directories that were both called an inbox are gone with it.

The on-disk migration runs with the schema one (FR-076) and is **destructive by
explicit decision** — no `.retired/` holding pen:

| Before                                       | After                   |
| -------------------------------------------- | ----------------------- |
| `knowledge/inbox/*.md` + `knowledge/*.md`    | flattened into `notes/` |
| `inbox/`                                     | `docs/`                 |
| `.raw/`                                      | unchanged               |
| `rules/`, `handoff/`, `superseded/`          | **deleted**             |
| `consolidation-log.md`, `knowledge/INDEX.md` | **deleted**             |

There is **no `MEMORY.md`** and no `INDEX.md` — both derived projections are
removed. Retrieval is not lane-scoped (FR-008a): `search`, `grep` and `recall`
all cover `notes/**/*.md` and `docs/**/*.md` at once, so a written note and an
uploaded document compete on relevance alone. Both lanes are source-of-truth and
DO sync.

`.history/` and `.raw/` are dot-prefixed deliberately: ripgrep skips hidden
entries, so `coffer__grep` never returns an archived revision or an uploaded
original alongside the live file, and neither is indexed for recall.
`.history/` **DOES sync** — it is recoverable source-of-truth history, the
sole safety net under an unattended rewrite — while `.raw/` holds the byte-exact
originals a `docs/` file was converted from.

A boot-time reindex sweep (`run_memory_reindex_sweep`) indexes any lane content
that reached disk while its store was not being searched.

The **periodic tidy** (`application/memory/reorg.py`, internal-LLM — FR-033/034)
is a bounded **agentic** loop: a langgraph `create_react_agent` (confined to
`infrastructure/llm` by Contract 9a, reached via an injected memory-local port)
driving four internal tools over `notes/` — `list_topics`, `read_topic`,
`write_topic`, `supersede_topic`. It merges duplicate and overlapping notes and
rewrites them into topic documents, splitting the over-long ones. The data-loss
guarantee is one invariant: **no byte leaves `notes/` without first being
archived** — a `write_topic` that overwrites an existing note copies the prior
revision to `.history/<slug>-<ts>.md` before writing, and
`supersede_topic` moves the note there. After the loop the pass reconciles the
index and records one row in Coffer's audit log; there is no per-scope
`consolidation-log.md` any more. The four tools are **internal LangChain
`StructuredTool`s** built from memory-local callables — never registered on the
MCP gateway, never agent-facing. Note `.md` frontmatter is `{title, description,
updated_at}` + body.

The pass is driven by a **`NotesTidyWorker`** (FR-035) shaped exactly like the
existing `RetentionWorker`: started from the app lifespan, one catch-up pass on
boot, then on an interval, with exceptions logged rather than killing the loop.
With no internal model configured it no-ops (`no_model`); with no notes it
no-ops (`empty`). The same pass is triggerable by hand from the detail page's
**Tidy** button and from `coffer knowledge organize`.

`organizer.py` and `organizer_prompt.py` are deleted: their job was to drain
`knowledge/inbox/` into topic documents, and with one flat lane that gradient no
longer exists. Deleted with them are `merge.py`, `merge_prompt.py`,
`merge_routes.py`, `rules_split.py`, `rules_files.py`, `handoff.py`,
`handoff_files.py`, `lane_reads.py`, `lane_deletes.py`, `lane_routes.py`, and
`knowledge_lane_cmd.py` less its retained `organize` command. `consolidate.py`
is **not** part of the tidy pass and is untouched — despite the name it is the
one-time startup heal for duplicate per-project scopes described above.

Per-note `.md` frontmatter:

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

`infrastructure/memory/paths.py` is the only module that constructs these paths. `infrastructure/memory/files.py` is the only module that reads/writes the per-item `.md` files and scans the two lanes for deltas.

## Cascade & integrity rules

| Action                                                | Effect                                                                                                                                                                                      |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `coffer__write` / user add                     | Write `notes/<note-slug>.md` → index into `documents`/`chunks`/FTS5/(vec) with `lane='notes'` → audit.                                                                         |
| Upload a document                              | Keep the original under `.raw/` → write the normalized `docs/<document>.md` → index with `lane='docs'` → audit.                                                               |
| User edit (REST/CLI/external editor)           | Rewrite `.md` → single re-index routine (sha256 changed → re-chunk/-embed) → audit. (A direct external-editor edit takes effect on the next lazy reindex-on-read.) MCP rewrites in place through `coffer__write(id=…)`. |
| Delete one item (MCP/REST/CLI)                 | Delete `.md` → remove `documents`/`chunks`/FTS5/vec rows → audit. `coffer__delete` covers a note or a document; a `docs/` delete takes its `.raw/` original with it.           |
| Clear a scope                                  | Delete every item under `notes/` and `docs/` (with `.history/` and `.raw/`) → remove all index rows → audit. Store Resource preserved.                                        |
| Tidy (interval worker, Tidy button, or `coffer knowledge organize`; internal agentic LLM) | A bounded langgraph `create_react_agent` loop over `notes/` with list/read/write/supersede tools: merge duplicates, rewrite notes into topic documents, split over-long ones. **Every overwrite/merge first copies the prior revision to `.history/<slug>-<ts>.md`** (never hard-delete). Then reconcile the index and audit `knowledge_tidied`. No internal model → no-op (`no_model`); no notes → no-op (`empty`). |
| Delete the store Resource                      | Remove `documents` rows for the store, `rmtree(store_dir)`, audit.                                                                                                            |
| Search / recall                                | **Lazy reindex-on-read**: scan both lanes for deltas (by `content_sha256`) → `reconcile` → search.                                                                            |
| Change embedding model                                | Allowed → re-embed the store on next index (files are truth).                                                                                                                               |
| Change `max_fact_chars`                               | Allowed.                                                                                                                                                                                    |

## The single re-index routine (`application/knowledge/reindex.py`, shared with KB)

```
compute content_sha256 of the new markdown
 ├ unchanged → skip (no-op)
 └ changed   → delete old chunks/FTS5/vec rows → re-chunk → (vector) re-embed
              → insert new → update documents row → audit *_UPDATED
```

All memory write paths (write, update, user edit, tidy pass, lazy reindex scan) funnel through this one routine.

The memory reconciler supplies its own **chunker** to the routine (per FR-032): the shared `infrastructure/knowledge/chunking.chunk_markdown`, bound to fixed memory chunk-size/overlap constants (not a per-store config), so a tidied topic document is split into **per-passage chunks** (heading- and block-structure aware) and search returns its most relevant passage. A short single-passage note still yields one chunk. The hidden `.history/` and `.raw/` directories are skipped by the scan, so an archived revision never competes with the live note.

When a vector-enabled store's embed degrades (embedding provider unavailable), the routine indexes keyword-only and persists an **empty-string `content_sha256`** — a deliberate never-matching sentinel so the next lazy reconcile retries the embed instead of treating the fact as up to date.

## Audit events added

| Value              | When emitted                                      |
| ------------------ | ------------------------------------------------- |
| `"memory_deleted"` | After a successful delete (MCP/REST/CLI)          |
| `"memory_cleared"` | After clearing a scope                            |
| `"knowledge_tidied"` | After a tidy pass that actually rewrote something  |

The destructive pair is audited because a delete leaves nothing behind. A write,
an edit and a reindex are not: they are recoverable and they leave their result
on disk — the file IS the record, and re-running any of them changes nothing a
reader would need the log to reconstruct.

The tidy pass earns its row for a different reason. It runs **unattended, on a
timer, with an LLM rewriting text the user and their agents wrote**, so the audit
log is the only place a reader can see that a pass ran, when, over which scope,
and what it touched. A pass that wrote and archived nothing left the notes
exactly as it found them and records nothing — the log is for changes something
made, not for a timer firing — the per-scope `consolidation-log.md` that used to carry
that story is deleted, and no page carries a tab for it. The recovery path is
`.history/`; the audit row is what tells you to go looking there.

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

**The read side is gone too.** The rules lane itself is deleted with the two-lane
redesign: `rules/` no longer exists on disk (FR-076 removes it), `rules_split.py`
and `rules_files.py` are deleted, and with them `GET /api/v1/knowledge/{scope}/rules`
and `coffer knowledge rules <scope>`. `application/knowledge/session_context.py`
keeps only the post-write `notify_change` hook. A rule is now simply a note: it
is written into `notes/` like anything else and found by search.

## Lane read endpoints (FR-053/FR-054)

The detail page presents a scope as **two tabs, Documents and Notes** (FR-053),
with a client-side filename filter above the tree — no search request, no third
tab. Server retrieval stays where it belongs: `coffer__search` for agents,
`coffer knowledge recall` for the CLI.

Both tabs read through the surviving lane reads (FR-054), addressed by **scope
name** (not cwd): they are thin **read projections of on-disk lane files**, no
LLM (resolve `store_dir` via the resolved scope, read via the lane path helper +
infra reader off the request thread). An empty scope returns an **empty list with
HTTP 200** — never a 404.

| Method + path                                | Returns           | Lane source                                     |
| -------------------------------------------- | ----------------- | ----------------------------------------------- |
| `GET /api/v1/knowledge/{name}/entries`       | `EntryListOut`    | `notes/*.md` — the Notes tab (`lane='notes'`).  |
| `GET /api/v1/knowledge/{name}/documents`     | `DocumentListOut` | `docs/*.md` — the Documents tab (`lane='docs'`). |

The handoff and consolidation-log endpoints are **deleted** with their lanes, as
are `HandoffOut`, `HandoffSceneOut` and `ConsolidationLogOut`; `lane_reads.py`,
`lane_deletes.py` and `lane_routes.py` go with them. Neither surviving read
exposes `.history/` or `.raw/` — the hidden directories are the tidy pass's
archive and the uploads' originals, not page content.

Both read DTOs surface the file's on-disk truth (absolute `.md` `path` +
containing `folder_path`) so each tab can offer the FR-021 open-in-editor /
reveal / copy-path affordances. Their schemas land in the OpenAPI contract owned
by the backend; the spec/data-model side documents only the shapes above.

## Wire contract (REST)

Lives in `contracts/api.openapi.yaml`. Routes under `/api/v1/memory_stores` (list/get/metrics; add/list/get/edit/delete/clear notes; upload/list/read/delete documents; search/grep/recall; `organize` as the manual tidy trigger). The handoff, rules, consolidation-log and merge routes are removed with their features. The write endpoints (add/edit/delete/clear) are retained — they are how agents (via MCP) and the CLI author notes; the web UI writes only by uploading a document or running a tidy pass, and never edits note text in-app. Read DTOs surface on-disk truth: `FactOut` carries the note's absolute `.md` `path` and its containing folder's `folder_path`, and `MemoryStoreOut` carries the store's absolute `store_dir`, so the viewer can offer open-in-editor / reveal. The kind-agnostic `/api/v1/resources/...` continues to work for memory stores. App-wide error envelope: `{ "error": { "code", "message", "details" } }`.

There is no longer a second, agent-scoped contract: `contracts/session-context.openapi.yaml` is deleted along with the `GET …/session-context` route it described (see "Rules delivery — removed" above).
