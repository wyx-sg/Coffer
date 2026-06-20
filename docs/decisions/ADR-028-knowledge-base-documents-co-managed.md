# ADR-028: Knowledge base documents are co-managed (agent-writable) with stable identity

> 中文版: [ADR-028-knowledge-base-documents-co-managed.zh.md](ADR-028-knowledge-base-documents-co-managed.zh.md)

**Status**: Accepted
**Date**: 2026-06-19
**Deciders**: Yuxing Wu
**Related**: spec `006-knowledge-base`; builds on [ADR-012](ADR-012-files-as-truth-sqlite-retrieval.md); sibling of [ADR-026 (memory via MCP)](ADR-026-memory-via-mcp-not-native-projection.md); part of the unified-knowledge redesign (知识 = 记忆 + 文档, both human + AI co-managed)

> **Amended (2026-06-20, simplification 5.7).** Decision 3 (per-document lock) is withdrawn: KB documents are always writable; the F01 audit trail plus vault backup replace the opt-out lock. Pillars 1 (ULID identity) and 2 (agents may write) stand.

## Context

The original `006-knowledge-base` design (ADR-012 era) framed the KB as a
**user-curated vault, read-only to agents**: agents read it through the MCP
gateway (`search` / `grep` / `read_document`) and could never write. Document
**identity was content-addressed** — the doc id (and the `<doc-id>.md` filename)
was the first 16 hex chars of the original file's `source_sha256`.

The unified-knowledge redesign reframes Coffer's knowledge as **知识 = 记忆
(notes) + 文档 (documents), both human + AI co-managed**. Memory (007) is already
agent-writable (`remember` / `update_memory` / `forget`). For the KB face to be a
living, co-managed knowledge store rather than a static vault, the asymmetry
"agents may write memory but never documents" is arbitrary — agents should be
able to contribute documents too, with the same guardrails memory has (F01
audit).

The content-addressed identity also has two concrete defects:

1. **Re-uploading an _updated_ version of the same file mints a new doc id** —
   because the bytes (and therefore the sha) changed — leaving the old version
   behind as a silent duplicate instead of updating the document in place.
2. **The id is opaque and unstable across edits.** Identity should be a stable
   _logical_ handle, decoupled from content; the content hash is provenance and
   a reindex no-op gate, not an identity.

## Decision

**KB documents are co-managed by humans and agents.** Three changes:

1. **Identity = a stable ULID**, minted at first ingest, not `source_sha256[:16]`.

   - `content_sha256` (hash of the Markdown body) stays as the reindex no-op
     gate; the original's `source_sha256` stays in `metadata` as provenance.
   - **Re-upload semantics** (matched by `original_filename` within a store):
     identical bytes are an **idempotent no-op**; a **changed** file with the
     same filename updates the **same document in place** (reuse the id; overwrite
     `docs/` + `raw/`, keeping only the latest original — no version history;
     `source_mode` resets to `converted`) and requires `replace=true`; a
     **different** filename is a new document with a new ULID.

2. **Agents may write KB documents** through new MCP gateway tools
   `coffer__add_document` / `coffer__edit_document` / `coffer__delete_document`,
   alongside the existing read tools. Every write funnels through the same single
   idempotent re-index routine humans use and is recorded in the F01 audit trail
   with the agent as actor.

## Scope & sequencing

This ADR ships the co-management **core at global scope**. Two related pieces of
the unified-knowledge redesign land with the later slice that surfaces them in
the unified 知识 UI, to keep this change reviewable and avoid building backend
state with no UI:

- **Per-project document scope** (the 全局/项目 axis for documents) — co-dependent
  with the unified 知识 project view; deferred to that slice.
- **Recoverable soft-delete (trash/restore)** — needs its own UI to be useful;
  for now delete is a hard delete that still leaves an F01 audit trail.

The in-app document viewer stays **read-only with external-editor affordances**
(the read-only-viewers decision): humans edit a document body via their external
editor or the edit API; agents edit via the MCP tools. This ADR does **not**
re-introduce an in-app text editor.

## Consequences

**Positive**

- The KB becomes a living, co-managed knowledge store consistent with the 知识
  model — symmetrical with agent-writable memory.
- Fixes the re-upload-updated-file duplicate bug: an updated source now updates
  its document in place under a stable id.
- Agent contributions are audited (F01) and reversible; a hard delete leaves an
  audit trail.

**Negative**

- Agents gain a **delete** capability over KB documents. Mitigated by the full
  F01 audit trail plus the vault backup; scoped deliberately because
  co-management without delete is half-measures.
- Stable ids mean the **same file uploaded into two KBs now has two ids** — KB
  documents are no longer deduplicated across stores. Accepted: each KB is its
  own corpus, and the per-store chunk-id namespacing already isolated them.

## Alternatives considered

**Keep the KB read-only to agents (status quo).** Rejected: it contradicts the
co-managed 知识 model and is arbitrarily asymmetric with agent-writable memory.

**Keep content-addressed identity.** Rejected: it causes the re-upload-duplicate
bug and conflates identity with content. A stable logical id with the content
hash kept as provenance is strictly better.

**Soft-delete now.** Deferred: a recoverable trash is only useful with a
restore UI, which belongs with the unified 知识 slice. Hard delete + F01 audit is
sufficient protection for this slice.

**Auto-update on every re-upload (no `replace` flag).** Rejected: silently
overwriting a document on a same-filename re-upload is surprising and can clobber
a hand-edited body; requiring `replace=true` for a changed file keeps the
overwrite explicit (the UI prompts "更新现有 / 新建").
