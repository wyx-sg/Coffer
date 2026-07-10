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
| `merged_identities`        | `list[str]`                                | Project ULIDs merged INTO this store (FR-058, amendment 2026-07-10). System-managed (never user-set); a resolve whose identity is listed here — and whose own store is gone — lands on this store. Syncs with the resource. Default `[]`. |

The embedding model is **mutable** — changing it re-embeds the store (files are truth). No immutability lock.

The shape difference vs spec 006 is deliberate: 007 keeps the embedding fields **flat** so the memory surface stays a thin form, while 006 nests them in an `EmbeddingConfig` object. Since the global-embedding redesign the flat fields are legacy — accepted on the wire for compatibility but ignored; indexing and recall both resolve the **global** embedding config. Likewise the recall response's `fallback` is a **boolean** in 007 — recall spans multiple stores, so a single fallback-mode string is ill-defined — whereas 006's single-store search reports a nullable mode enum (`fallback: "keyword" | null`).

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
    title          TEXT NOT NULL,               -- memory: frontmatter `title`
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

**One store per repo, across git worktrees.** The project ULID is `sha256(git-root path)`. A linked git worktree has its own `.git` *file*, so `git_root` (`infrastructure/memory/scope_fs.py`) follows that pointer's `gitdir`/`commondir` to the **main** repo toplevel — every worktree of a repo (and the main checkout) resolves to one ULID, hence one store. Branch resolution (`git_branch`) stays per-worktree, since handoffs are branch-keyed. Stores fragmented by the earlier path-hash-per-worktree behaviour are healed at daemon startup by a one-time, idempotent, additive consolidation (`application/memory/consolidate.py`): it re-resolves each `project_root`, and any store whose name is no longer the canonical `project-<ULID>` for its root has its lane files merged (journal deduped by timestamp, other collisions kept as `--from-<ulid>` siblings) into the canonical store and is then retired (resource + `documents` + label + root rows).

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
    │   └── rules/*.md                 # procedural lane: rules.md + per-topic <slug>.md after split (store ROOT; outside recall; injected; DOES sync)
    └── projects/<project-ulid>/       # one dir per project
        ├── knowledge/
        │   ├── inbox/<item>.md
        │   ├── <topic>.md
        │   └── INDEX.md
        ├── consolidation-log.md
        ├── superseded/<slug>-<ts>.md
        ├── rules/*.md                    # rules.md + per-topic <slug>.md (autonomous split past the threshold)
        └── journal/<YYYY-MM-DD>.md       # episodic, append-only, one file PER DAY (a day with no entry → no file); indexed for recall (FR-043)
```

There is **no `MEMORY.md`** — the prior derived projection is removed. `recall` globs `knowledge/**/*.md` (excluding `INDEX.md`), so it transparently picks up topic docs once the organizer writes them and finds a hand-written topic doc immediately. `INDEX.md` and the store-root `consolidation-log.md` are **derived/machine-local**: excluded from recall and from the sync mirror (each machine regenerates `INDEX.md` from the synced topic docs; the log is per-machine). Topic docs themselves are source-of-truth and DO sync. The store-root **`superseded/`** tombstone holds prior versions retired by the reorg pass (FR-033/034): like `handoff/` it sits outside the `knowledge/` lane so it is **excluded from recall**, but unlike the derived files it **DOES sync** — it is recoverable source-of-truth history, not a regenerated artifact. The store-root **`rules/`** lane is the **procedural lane** (FR-036): the organizer classifies rule-shaped inbox items into `rules/rules.md` (append, not topic-merge); once any rules file exceeds the threshold the organizer's reorg pass splits it by topic into per-category `rules/<slug>.md` files (amendment 2026-06-22), and the read surface concatenates every `rules/*.md`. It sits outside the `knowledge/` lane so it is **excluded from recall** (rules are delivered by session-start injection, a later slice, not by `recall`), and it **DOES sync** as source-of-truth (like `handoff/`). It is read-only over `GET /memory_stores/{name}/rules` / `coffer memory rules`. The store-root **`journal/`** lane is the **episodic lane** (FR-040): unlike `rules/`/`handoff/`/`superseded/` it **participates in recall** — the reconciler indexes each `journal/<YYYY-MM-DD>.md` (one file per day; a day with no entry creates no file) as one memory document (chunked like topic docs) and the grep guard keeps `journal/` hits, so episodic events are searchable (FR-043). Indexing is **eager**: `JournalService.append` indexes the period file immediately (reconcile-on-append) so a distilled entry is recall-able without waiting for a lazy reconcile-on-read, and a boot-time reindex sweep (`run_memory_reindex_sweep`) indexes any journal that was written to disk while its store was not being recalled. It still **DOES sync** as source-of-truth history and is **not** counted in a store's `fact_count` (that counts only the `knowledge/` lane).

The **organizer** (`application/memory/organizer.py`, internal-LLM, explicit `organize` trigger only) drains `inbox/` into the topic docs via a one-shot completion per item: retrieve up to 3 candidate topic docs (no LLM) → one LLM merge/create call → write `knowledge/<slug>.md` → delete the inbox item (only after the write succeeds) → append a changelog line. A malformed LLM response skips the item (left in inbox, never corrupts a doc). Topic-doc `.md` frontmatter is `{title, description, updated_at}` + body. The langchain LLM call stays in `infrastructure/chat` (Contract 9); `application/memory` reaches it through a memory-local `LlmCompletionPort` (clone of the distill slice; Contract 5e forbids importing `application.distill`).

The **reorg pass** (`application/memory/reorg.py`, internal-LLM, explicit `reorg` trigger only — FR-033/034) deepens the organizer with an **agentic** loop: a bounded langgraph `create_react_agent` (confined to `infrastructure/chat` by Contract 9, reached via an injected memory-local port — clone of the agentic-RAG slice) driving four internal tools over the topic docs — `list_topics`, `read_topic`, `write_topic`, `supersede_topic`. It consolidates duplicate/overlapping docs and splits over-long ones. The data-loss guarantee is one invariant: **no byte leaves the `knowledge/` lane without first being archived** — a `write_topic` that overwrites an existing doc archives the prior version to `superseded/<slug>-<ts>.md` before writing, and `supersede_topic` moves the doc there. After the loop the pass regenerates `INDEX.md`, reconciles, and audits `memory_reorganized`. The four tools are **internal LangChain `StructuredTool`s** built from memory-local callables — never registered on the MCP gateway, never agent-facing.

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
| Lane delete (REST)                             | `DELETE /memory_stores/{name}/{journal/<period>,handoff/<branch>,rules,consolidation-log}` → remove the lane file(s) → drop the journal lane's index rows (FR-043; handoff/rules are outside recall) → append one human-readable line to `consolidation-log.md` (EXCEPT the changelog's own delete) → audit `memory_deleted`. A missing lane file → 404 (mirrors fact-delete). |
| Clear a scope                                  | Delete every memory item under `knowledge/` → remove all index rows → audit. Store Resource preserved.                                                                        |
| Organize (explicit trigger; internal LLM)      | Per inbox item: retrieve ≤3 candidate topic docs → one-shot LLM merge/create/**classify** → if the LLM marks the item a **rule**, append it to `rules/rules.md` (procedural lane, FR-036); else write `knowledge/<slug>.md` → delete the inbox item (only after the write/append) → append `consolidation-log.md`. Then regenerate `INDEX.md`, reconcile the index, **split any over-threshold `rules/*.md` file into per-topic `rules/<slug>.md` via a one-shot LLM classify** (amendment 2026-06-22), audit `memory_organized` (with a `rules_appended` count). Malformed LLM output skips the item (stays in inbox); no internal model → no-op. |
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

### Rules-injection audit events (slice 6, FR-049/FR-052)

| Value                          | When emitted                                                       |
| ------------------------------ | ----------------------------------------------------------------- |
| `"agent_hook_installed"`       | After Coffer installs its SessionStart (+ SessionEnd for Claude Code) hook entry into an agent's hooks config |
| `"agent_hook_uninstalled"`     | After Coffer removes its hook entry from an agent's hooks config   |
| `"agent_native_memory_disabled"`  | After `disable_native_memory` is turned ON and the agent's native-memory off-switch is written (FR-052) |
| `"agent_native_memory_restored"`  | After `disable_native_memory` is turned OFF (or the hook is uninstalled) and the agent's prior native-memory setting is restored (FR-052) |

These four events live on the **agent** surface (spec 004), recorded by the
`AgentHookService` / native-memory toggle; they carry the agent name and the
config file touched only — never any rules-bundle or memory content. The
SessionStart/SessionEnd hook callbacks themselves write through spec 007's
existing memory paths: a session-end distill reuses the `memory_added` /
`journal_append` events (no distinct audit event, like the FR-046 sweep), and a
session-context read emits no audit event (it is a read).

## Rules runtime injection (slice 6 — FR-049–FR-052)

Slice 6 delivers the rules lane (FR-036) into each managed agent at runtime by
**installing session hooks** that call back to Coffer for a **context-only**
bundle — never a native file write (ADR-026). The agent-config plumbing
(`AgentConfig`, hook install/uninstall, native-memory toggle) lives in spec
**004-agent-registry**; the bundle assembly and the session-end distill reuse
spec 007's memory paths. This section documents the 007-facing shapes; the
`AgentConfig` field and the hook-install / native-memory REST trio are added to
spec 004's data-model + `004-agent-registry/contracts/api.openapi.yaml`.

### `AgentConfig.disable_native_memory` (spec 004 domain)

A new boolean field on the agent's persisted config, **default `false`** (the
ADR-026 posture — Coffer never touches native memory). Surfaced on `AgentPatch`
(settable) and `AgentOut` (readable).

| Field                   | Type   | Notes                                                                                          |
| ----------------------- | ------ | ---------------------------------------------------------------------------------------------- |
| `disable_native_memory` | `bool` | Default `false`. When `true`, Coffer writes the agent's native-memory off-switch and restores it on toggle-off/uninstall (FR-052). The migration validator is tolerant (a config without the key reads as `false`). |

When set `true`, Coffer writes:

- **Claude Code** — `~/.claude/settings.json`: `{"autoMemoryEnabled": false}` (JSON, atomic, `.bak`). Restore removes the key.
- **Codex** — `~/.codex/config.toml`: `features.memories = false` + `memories.generate_memories = false` (TOML, tomlkit, atomic, `.bak`). Restore removes both keys.

### Installed hook entries shape

Coffer installs its hook into the agent's top-level `hooks` key (Claude Code
`settings.json`; Codex `hooks.json` — same JSON schema). The command is the
absolute path to the `coffer-hook` console script with the agent name baked in
(`coffer-hook --agent <name>`), since the hook stdin JSON does not carry Coffer's
agent identity (cwd / session_id / event come from stdin). Install/uninstall are
idempotent and recognise **only** Coffer's own entry by the `coffer-hook`
command basename — user hooks are never touched.

```jsonc
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          { "type": "command", "command": "/abs/path/to/coffer-hook --agent claude-code" }
        ]
      }
    ],
    // Claude Code ONLY — Codex has no session-end event (FR-051).
    "SessionEnd": [
      {
        "matcher": "clear|logout|prompt_input_exit|other",
        "hooks": [
          { "type": "command", "command": "/abs/path/to/coffer-hook --agent claude-code" }
        ]
      }
    ]
  }
}
```

**SessionStart contract** (both agents): the hook reads stdin
`{session_id, transcript_path, cwd, hook_event_name, source, …}`, calls
`GET …/session-context?cwd=<cwd>`, and prints
`{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<bundle>"}}`
then exits 0 (bundle ≤ 10k chars). **Any** failure (no daemon, timeout, error) →
print nothing, exit 0 (never blocks the agent). **SessionEnd contract** (Claude
Code only): the hook reads stdin `{session_id, transcript_path, cwd, reason}`,
calls `POST …/sessions/{session_id}/end` with `{cwd}`, ignores the result, exits 0.

### Bundle assembly (`assemble_session_context(cwd) -> str`, FR-049/FR-050)

Resolve the recall scopes for `cwd` → for each scope read its rules (every
`rules/*.md` concatenated, FR-036 read surface) → concatenate **project rules
first, then global** →
append the **two seeded built-in rules** (constants, always present even when the
rules lanes are empty):

- **seeded resume rule** — when the user wants to continue prior work, call `coffer__resume()` to pull the saved working-state handoff for this project + branch.
- **seeded soft-steer rule** — prefer `coffer__remember` / `coffer__recall` over the agent's native memory; Coffer is the shared store across the user's agents.

The handoff body is **not** in the bundle (pull-on-demand via `coffer__resume`,
FR-050). Returns markdown; an empty result still carries the seeded rules.

### New endpoints (slice 6)

Two agent-scoped endpoints back the hooks. They live alongside the other
`/api/v1/agents/{name}/…` routes in `contracts/transcripts.openapi.yaml` (the
agent-scoped 007 contract); see the wire-contract note below.

| Method + path                                              | Body / query | Returns | Notes |
| ---------------------------------------------------------- | ------------ | ------- | ----- |
| `GET /api/v1/agents/{name}/session-context?cwd=`           | `cwd` query  | `{additional_context: string}` | SessionStart bundle (FR-049/FR-050). Read-only; no audit. `cwd` outside a git project → global + seeded rules only. |
| `POST /api/v1/agents/{name}/sessions/{session_id}/end`     | `{cwd}`      | `202`/`200` | SessionEnd distill (FR-051). Idempotent via the `distilled_sessions` ledger; no-op when already distilled / no model / not a git project. |

The hook-install trio (`GET/POST/DELETE /api/v1/agents/{name}/hook-install`,
cloning `/mcp-install`) and the `disable_native_memory` field on `PATCH
/api/v1/agents/{name}` live in spec **004-agent-registry** (where `AgentOut` /
`AgentPatch` / `/mcp-install` already live), not here.

### `distilled_sessions` idempotency ledger (shared with FR-046)

The SessionEnd distill (FR-051) reuses the **same** machine-local ledger keyed by
`(agent, session_id, content_sha256)` introduced for the FR-046 catch-up sweep —
a session is never double-distilled across the two paths (the hook lowers
latency; the sweep is the standalone write guarantee). No new ledger table is
introduced for slice 6.

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

## Four-lane read endpoints (slice 7 — FR-053/FR-054)

The memory store detail page presents the store as four lane sections
(Knowledge / Rules / Journal / Handoff) plus a consolidation-changelog view
(FR-053). Knowledge reuses the existing fact read surface (`GET …/facts`) and is
what `recall` operates over; Rules already has `GET …/{name}/rules` (FR-036).
Slice 7 adds three more **read-only** lane endpoints (FR-054), each addressed by
**store name** (not cwd) — they are thin **read projections of on-disk lane
files**, no LLM, mirroring `get_rules`/metrics on `MemoryService` (resolve
`store_dir` via the resolved scope, read via the lane path helper + infra reader
off the request thread). An empty store returns an **empty list / `null` with
HTTP 200** — never a 404.

| Method + path                                        | Returns               | Lane source                                                                 |
| ---------------------------------------------------- | --------------------- | -------------------------------------------------------------------------- |
| `GET /api/v1/memory_stores/{name}/journal`           | `JournalOut`          | `journal/<YYYY-MM-DD>.md` files (one per day), **newest period first** (episodic; FR-040). |
| `GET /api/v1/memory_stores/{name}/handoff`           | `HandoffOut`          | `handoff/<branch-slug>.md` scenes, one per branch (continuity; FR-023).     |
| `GET /api/v1/memory_stores/{name}/consolidation-log` | `ConsolidationLogOut` | `consolidation-log.md` at the store root; `text = null` when absent (FR-031). |

### Response entities (read-only projections)

These are **read DTOs only** — not new domain entities or tables. Each surfaces
the lane file's on-disk truth (absolute `.md` `path` + containing `folder_path`)
so the read-only lane views can offer the FR-021 open-in-editor / reveal /
copy-path affordances, exactly like `FactOut`.

**`JournalFileOut`** — one time-partitioned journal file.

| Field         | Type  | Notes                                                       |
| ------------- | ----- | ----------------------------------------------------------- |
| `period`      | `str` | `YYYY-MM-DD` stem of the `journal/<period>.md` file (one per day). |
| `text`        | `str` | The journal file's markdown body.                           |
| `path`        | `str` | Absolute on-disk `.md` path of the journal file.            |
| `folder_path` | `str` | Absolute path of the containing `journal/` folder.          |

**`JournalOut`**

| Field   | Type                | Notes                                                            |
| ------- | ------------------- | --------------------------------------------------------------- |
| `files` | `JournalFileOut[]`  | Journal files **newest period first**; empty list for an empty store. |

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

**`ConsolidationLogOut`** — the organizer's append-only 固化 changelog.

| Field         | Type          | Notes                                                            |
| ------------- | ------------- | ---------------------------------------------------------------- |
| `text`        | `str \| None` | The `consolidation-log.md` body; `null` when the file is absent. |
| `path`        | `str`         | Absolute on-disk path of `consolidation-log.md` (store root).    |
| `folder_path` | `str`         | Absolute path of the containing store directory.                 |

These read endpoints (with their schemas) land in the OpenAPI contract owned by
the backend; the spec/data-model side documents only the shapes above.

## Wire contract (REST)

Lives in `contracts/api.openapi.yaml`. Routes under `/api/v1/memory_stores` (list/get/metrics; add/list/get/edit/delete/clear facts; recall; the slice-7 journal/handoff/consolidation-log lane reads of FR-054). The write endpoints (add/edit/delete/clear) are retained — they are how agents (via MCP) and the CLI author facts; the desktop/web UI is a read-only viewer. Read DTOs surface on-disk truth: `FactOut` carries the fact's absolute `.md` `path` and its containing folder's `folder_path`, and `MemoryStoreOut` carries the store's absolute `store_dir`, so the read-only viewer can offer open-in-editor / reveal. The kind-agnostic `/api/v1/resources/...` continues to work for memory stores. App-wide error envelope: `{ "error": { "code", "message", "details" } }`.

The slice-6 agent-scoped endpoints (`GET …/session-context`, `POST …/sessions/{session_id}/end`) live in `contracts/transcripts.openapi.yaml` alongside the other `/api/v1/agents/{name}/…` routes; the hook-install trio and the `disable_native_memory` agent field live in `004-agent-registry/contracts/api.openapi.yaml` (see "Rules runtime injection" above).
