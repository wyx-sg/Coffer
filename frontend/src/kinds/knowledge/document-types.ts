// frontend/src/kinds/knowledge/document-types.ts
//
// Wire types for the DOCUMENT lane of a knowledge scope: files someone ingested
// (any format, normalized to Markdown on disk) under `<scope>/inbox/`. Split
// from types.ts for the file-size budget; api.ts re-exports both so call sites
// see one surface.
//
// Documents are a different lane from entries: `document_count` counts only
// these, and a documents read never returns entries. Do not conflate them.

import type { RetrievalMode } from "./types";

export type SourceMode = "converted" | "edited";

export interface DocumentOut {
  id: string;
  kind: string;
  resource_name: string;
  title: string;
  description?: string | null;
  source_mode: SourceMode;
  content_sha256: string;
  /** The scope's project id (project ULID, global sentinel, or collection name). */
  project_id: string;
  chunk_count?: number;
  metadata: Record<string, unknown>;
  /** Per-document embed status: done | embedding | queued | running | error
   * (absent when the async batch service is not wired). */
  embed_status?: string | null;
  /** Absolute on-disk path of the document's Markdown file (FileActions). */
  path?: string;
  /** Absolute on-disk path of the document's containing folder. */
  folder_path?: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentListOut {
  documents: DocumentOut[];
  total: number;
}

export interface DocumentDetailOut extends DocumentOut {
  markdown: string;
}

export interface ReembedBatchRequest {
  document_ids?: string[];
  /** Re-embed every document still pending an embed (re-embed-all). */
  all?: boolean;
}

export interface ReembedBatchResponse {
  queued: number;
  skipped: number;
  total: number;
}

export interface DocumentEmbedStatus {
  document_id: string;
  state: string;
  message?: string | null;
}

export interface DocumentStatusResponse {
  // Only in-flight documents appear (queued / running / error).
  statuses: DocumentEmbedStatus[];
}

export interface Passage {
  text: string;
  document_id: string;
  title: string;
  score: number;
  position: number;
}

export interface SearchResponse {
  // External retrieval is "one query → one answer": the backend auto-selects
  // the strategy, so the response carries only ranked passages — no `mode`,
  // no `fallback`.
  passages: Passage[];
}

export interface ReindexResult {
  documents_scanned: number;
  documents_reindexed: number;
  documents_skipped: number;
  /** Rows pruned because their markdown file was removed out-of-band. */
  documents_removed?: number;
  /** Docs indexed keyword-only because the embedding provider was unavailable. */
  documents_degraded?: number;
}

export interface GrepHit {
  path: string;
  line_number: number;
  line: string;
}

export interface GrepResponse {
  hits: GrepHit[];
  truncated: boolean;
}

// One of five outcomes per document when scanning its external source file:
// unchanged, changed (re-ingestable), missing (file gone), edited (source
// changed but the doc was locally edited so update is skipped), or updated
// (was changed and auto-re-ingested because auto_update_sources is on).
export type SourceStatus = "unchanged" | "changed" | "missing" | "edited" | "updated";

export interface SourceStatusEntry {
  document_id: string;
  title: string;
  source_path: string;
  status: SourceStatus;
}

export interface SourceCheckResponse {
  // Only documents with a tracked source_path appear (web uploads are untracked).
  sources: SourceStatusEntry[];
}

/** Re-exported so document surfaces need only one import path. */
export type { RetrievalMode };
