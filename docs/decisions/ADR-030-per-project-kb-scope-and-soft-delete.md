# ADR-030: Per-project knowledge-base document scope and recoverable soft-delete

> 中文版: [ADR-030-per-project-kb-scope-and-soft-delete.zh.md](ADR-030-per-project-kb-scope-and-soft-delete.zh.md)

**Status**: Accepted
**Date**: 2026-06-19
**Deciders**: Yuxing Wu
**Related**: specs `006-knowledge-base`, `007-memory`; completes [ADR-028 (co-managed documents)](ADR-028-knowledge-base-documents-co-managed.md); builds on [ADR-012 (files as truth)](ADR-012-files-as-truth-sqlite-retrieval.md); sibling of [ADR-026 (memory via MCP)](ADR-026-memory-via-mcp-not-native-projection.md); the slice that completes the unified-knowledge redesign (知识 = 记忆 + 文档 × 全局 / 项目)

## Context

[ADR-028](ADR-028-knowledge-base-documents-co-managed.md) shipped the co-management
core **at global scope** and explicitly deferred two pieces "to the later slice
that surfaces them in the unified 知识 UI, to keep this change reviewable and
avoid building backend state with no UI":

- **Per-project document scope** — the 全局 / 项目 axis for documents.
- **Recoverable soft-delete** (trash / restore) — "needs its own UI to be useful".

This ADR makes both decisions, as that unified-知识 slice lands.

Two facts frame it:

1. **Memory (007) already has a two-layer scope**: a global store (the
   `WORKSPACE_GLOBAL` sentinel `project_id`) and a per-project store keyed by a
   **project ULID** deterministically derived from the agent's git-root path
   ([ADR-026](ADR-026-memory-via-mcp-not-native-projection.md) era). The KB face
   carried the sentinel on **every** row. The unified 知识 model — 知识 = 记忆
   (notes) + 文档 (documents) × 全局 / 项目 — needs documents to live per-project
   too, so a project's notes and documents sit together under one scope.
2. **Delete was a hard delete.** ADR-028 accepted that as a temporary measure,
   protected by the F01 audit trail and the per-document lock. With the unified UI
   giving documents a real management surface, a recoverable trash is now both
   feasible and expected.

## Decision

### 1. Per-project document scope

- A KB document carries a **real `project_id`**: the `WORKSPACE_GLOBAL` sentinel
  for a global document, or a **project ULID** (deterministic Crockford-base32 of
  the git-root path — the *same* `project_ulid` memory uses) for a project-scoped
  document. `project_id` was already a column on `documents`; this populates it
  for the KB face instead of always stamping the sentinel.
- **On-disk layout gains a per-project subtree, back-compatibly.** Global
  documents stay at `knowledge/<kb>/docs/` + `raw/` (existing documents are not
  relocated); project documents live at
  `knowledge/<kb>/projects/<ulid>/docs/` + `raw/`. The asymmetry is deliberate —
  it mirrors memory's `global/` + `projects/<ulid>/` split without moving any
  already-stored global document.
- **Re-upload identity is scoped to `(kb, project_id)`.** The same filename in
  global vs a project, or across two projects, is an independent document.
  (`find_by_filename` already takes `project_id`.)
- **List, read, grep, and keyword / vector search are scoped to the resolved
  `project_id`.** Grep is naturally scoped (it walks the scope's `docs/` dir);
  keyword / vector filter on `documents.project_id`.
- **Scope resolution at the boundary, not in the service.** The REST ingest
  endpoint accepts an explicit `project_id` (the unified UI sends the scope the
  user is viewing); agent MCP writes resolve the project from the agent's reported
  `cwd` (git-root → `project_ulid`), defaulting to global when there is no git
  root or no `cwd`. The git-root → ULID helpers (`scope_fs`) move from
  `infrastructure/memory/` into the shared `infrastructure/knowledge/` substrate so
  both faces share one implementation without a forbidden cross-kind import.

### 2. Recoverable soft-delete (trash / restore)

- `documents` gains a **nullable `deleted_at`**. Deleting a *live* document is a
  **soft-delete**: it removes `docs/<id>.md` and the index rows (chunks / FTS5 /
  vec) but **KEEPS** `raw/<id>.<ext>` and the `documents` row with `deleted_at`
  set. The document leaves every live read — list, get, search, grep, metrics, and
  the re-upload match — all of which filter `deleted_at IS NULL`.
- **Restore** re-converts the document from its kept `raw/` original, regenerates
  `docs/<id>.md`, re-indexes, and clears `deleted_at`. `source_mode` resets to
  `converted`: a restored document is freshly converted from the original. Any
  pre-deletion body **edits are not recovered** — soft-delete removed the edited
  markdown and only the original `raw/` is kept (consistent with ADR-028's
  "keep only the latest original — no version history").
- **Deleting an already-trashed document purges it permanently** (removes `raw/` +
  the row). So "delete" on a live document trashes it; "delete" on a trashed
  document is the explicit permanent purge. A **KB-level** delete still hard-removes
  everything, including the trash.
- The **lock (FR-021) still guards**: a locked document cannot be soft-deleted,
  purged, or restored-over.
- **Reindex-on-read must not resurrect a tombstone**, and the guard is two-sided:
  because soft-delete removes `docs/<id>.md`, the scan's *rebuild* branch (file
  present, no row → reconstruct) never sees the file; and because the *prune*
  branch (row present, file gone → hard-delete) operates over **live rows only**
  (`list_documents` filters `deleted_at IS NULL`), it never hard-deletes the
  tombstone. The kept `raw/` is intentionally not scanned — only `docs/` is the
  markdown truth — so it cannot trigger a rebuild.
- **Audit**: soft-delete records `KB_DOCUMENT_DELETED` (the existing event, now
  meaning "moved to trash"); restore records `KB_DOCUMENT_RESTORED`; permanent
  purge records `KB_DOCUMENT_PURGED`.

### Why the shared-repo filter is safe for memory

The `documents` table and its repo are shared with the memory face. Adding
`deleted_at IS NULL` to the repo reads is a **no-op for memory rows**: memory never
sets `deleted_at` (memory's `forget` is a hard delete of a fact file + its row), so
its rows always satisfy the predicate and its behavior is unchanged.

## Consequences

**Positive**

- Completes the unified 知识 model: a project's notes (memory) and documents (KB)
  now live under one 全局 / 项目 axis, surfaced together.
- Agent deletes become **recoverable** (soft-delete) — a strictly safer default for
  co-managed documents than the ADR-028 hard delete, while purge stays explicit.
- The existing global corpus is untouched on disk; per-project documents are
  additive.

**Negative / trade-offs**

- **Restore loses body edits** (it re-converts from `raw/`). Accepted: there is no
  version history (ADR-028), and a curated/edited document should be **locked**,
  which prevents its deletion entirely.
- **The trash is unbounded** until purged or the KB is deleted (no auto-expiry).
  Accepted for a single-user local tool; purge is explicit and a KB-delete clears
  it.
- `search` / `grep` gain `project_id` scoping while the FTS / vec index stays
  keyed by `(kind, resource_name)`. **grep** scopes by the per-scope `docs/`
  directory. **keyword** search filters at the existing FTS↔`documents` JOIN
  (`AND d.project_id = :pid`), so `LIMIT k` returns the true top-k in-scope — no
  over-fetch. **vector** search is the exception: the sqlite-vec KNN has no
  `project_id`, so it over-fetches the KNN, filters at the JOIN, and truncates to
  `top_k` — its recall is bounded by the over-fetch ceiling, accepted because
  vector is opt-in and corpora are small (SC-002 ≤ 50 documents).
- A document's scope is **fixed at ingest**; "moving" a document between global and
  a project is a re-ingest, not a metadata flip. Accepted to keep the on-disk truth
  and the stable id intact.

## Alternatives considered

**Per-project = a separate KB resource per project** (mirroring how memory makes a
`project-<ulid>` Resource). Rejected: it fragments one corpus into N resources and
breaks "one KB, scoped views". Scoping within one KB resource by the `project_id`
column keeps a single corpus with a scope axis.

**Soft-delete keeps `docs/<id>.md`** (move it to a `trash/` subtree) to preserve
edits. Rejected for this slice: it complicates reindex-on-read (the scan would have
to learn to skip a trash subtree) and re-introduces version-history-like state;
re-converting from the kept `raw/` is simpler and keeps "files in `docs/` are the
live truth" honest.

**Tombstone via a `status` / boolean column** instead of a `deleted_at` timestamp.
Rejected: `deleted_at` doubles as the trash-ordering key and the "when" for the
restore / audit UX; a boolean carries less for no saving.

**No purge — a KB-delete is the only cleanup.** Rejected: an unbounded trash with no
per-document purge is a footgun. Making "delete a trashed document = purge" is the
least-surprising affordance and needs no new verb.
