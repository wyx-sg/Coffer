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
  mode: RetrievalMode;
  fallback?: RetrievalMode | null;
  passages: Passage[];
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

export interface ReindexResult {
  documents_scanned: number;
  documents_reindexed: number;
  documents_skipped: number;
}

export interface KnowledgeBaseMetrics {
  document_count: number;
  chunk_count: number;
  indexed_modes: RetrievalMode[];
  disk_bytes: number;
}
