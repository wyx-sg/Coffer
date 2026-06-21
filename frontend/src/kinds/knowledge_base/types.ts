// frontend/src/kinds/knowledge_base/types.ts
//
// Wire types for the redesigned `knowledge_base` kind (spec 006). Split out of
// api.ts to keep that file under the size limit; api.ts re-exports everything
// here so existing `import { … } from "./api"` call sites are unaffected.

export type RetrievalMode = "grep" | "keyword" | "vector";

export interface EmbeddingConfig {
  provider: string;
  model: string;
  base_url?: string | null;
  credential_ref?: string | null;
  dimensions: number;
}

export interface KnowledgeBaseConfigOut {
  enabled_modes: RetrievalMode[];
  default_mode: RetrievalMode;
  chunk_size: number;
  chunk_overlap: number;
  max_document_bytes: number;
  embedding?: EmbeddingConfig | null;
  // When true, a `check-sources` scan re-ingests documents whose external
  // source file changed (FR-021..024). The settings PATCH replaces the whole
  // config, so this MUST be carried through or it silently resets to false.
  auto_update_sources: boolean;
}

export interface KnowledgeBaseOut {
  ref: string;
  kind: string;
  name: string;
  description: string | null;
  config: KnowledgeBaseConfigOut;
  enabled: boolean;
  /** Number of documents in the KB (shown in the knowledge-bases table). */
  document_count?: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeBaseListOut {
  knowledge_bases: KnowledgeBaseOut[];
}

export type SourceMode = "converted" | "edited";

export interface DocumentOut {
  id: string;
  kind: string;
  resource_name: string;
  title: string;
  description?: string | null;
  source_mode: SourceMode;
  content_sha256: string;
  /** WORKSPACE_GLOBAL sentinel for global KB documents (per-project scope is a later slice). */
  project_id: string;
  chunk_count?: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DocumentListOut {
  documents: DocumentOut[];
  total: number;
}

export interface DocumentDetailOut extends DocumentOut {
  markdown: string;
  /** Absolute on-disk path of the document's Markdown file (FileActions). */
  path?: string;
  /** Absolute on-disk path of the document's containing folder. */
  folder_path?: string;
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
}

export interface KnowledgeBaseMetrics {
  document_count: number;
  chunk_count: number;
  // Documents indexed keyword-only because the embedding provider was
  // unavailable (the embed is retried on the next reconcile). 0 when all embed.
  documents_degraded: number;
  indexed_modes: RetrievalMode[];
  disk_bytes: number;
}

// One of five outcomes per document when scanning its external source file
// (FR-021..024): unchanged, changed (re-ingestable), missing (file gone),
// edited (source changed but the doc was locally edited so update is skipped),
// or updated (was changed and auto-re-ingested because auto_update_sources is on).
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
