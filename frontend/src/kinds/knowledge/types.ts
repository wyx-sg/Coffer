// frontend/src/kinds/knowledge/types.ts
//
// Wire types + scope helpers for the one `knowledge` kind. `memory` and
// `knowledge_base` used to be two kinds with two of everything; they are one
// resource kind now, and a SCOPE is simply where a piece of knowledge belongs:
//
//   global          — follows the user everywhere; auto-provisions on first use
//   project-<ULID>  — resolved from the cwd's git root; auto-provisions
//   any other name  — a collection the user created deliberately (never auto)
//
// A scope holds two lanes: ENTRIES an agent wrote (`<scope>/knowledge/`) and
// DOCUMENTS someone ingested (`<scope>/inbox/`). The counts are separate on
// purpose — never sum or conflate them.
//
// The knowledge routes are not in the mcp-gateway OpenAPI contract that
// `npm run codegen` reads, so these are hand-written like the sibling kinds'.
// Document-side shapes live in ./document-types; api.ts re-exports both.

export type RetrievalMode = "grep" | "keyword" | "vector" | "hybrid";

/** Which of the three a scope is; derived from the name by the backend. */
export type ScopeKind = "global" | "project" | "named";

/**
 * Who authored a knowledge entry. Mirrors the backend
 * `coffer.domain.knowledge.entry.Actor`. This is the entry-authorship
 * vocabulary — distinct from the broader audit-log actor vocabulary (request
 * origins `ui`/`cli`/`api` plus the domain actors) rendered via `audit.actor.*`.
 */
export type KnowledgeActor = "agent" | "user";

/** Sentinel `project_id` for installation-global resources (C01); mirrors the
 * backend's `WORKSPACE_GLOBAL_PROJECT_ID`. */
export const WORKSPACE_GLOBAL_PROJECT_ID = "00000000000000000000000000";

export const GLOBAL_SCOPE_NAME = "global";
export const PROJECT_SCOPE_PREFIX = "project-";

/**
 * Which kind of scope a resource NAME denotes — the same rule the backend
 * applies (`scope_kind_of`), so the two can never disagree. Used by surfaces
 * that only have a generic `ResourceOut` row (no typed `scope` field).
 */
export function scopeKindOf(name: string): ScopeKind {
  if (name === GLOBAL_SCOPE_NAME) return "global";
  if (name.startsWith(PROJECT_SCOPE_PREFIX)) return "project";
  return "named";
}

/**
 * Derive a scope kind from whatever the caller actually has.
 *
 * The typed `/knowledge` rows carry an explicit `scope`; a generic `ResourceOut`
 * row carries neither that nor `project_id` at the top level, so fall back to
 * the config, then to the name (which always encodes the answer). Returns
 * `null` only when there is no name at all.
 */
export function deriveScope(source: {
  scope?: unknown;
  name?: unknown;
  project_id?: unknown;
  // `unknown` so any caller's config shape (the typed ScopeOut, a generic
  // ResourceOut config, a test fixture) is accepted; read defensively.
  config?: unknown;
}): ScopeKind | null {
  const cfg = (source.config ?? undefined) as { scope?: unknown; project_id?: unknown } | undefined;
  const explicit = source.scope ?? cfg?.scope;
  if (explicit === "global" || explicit === "project" || explicit === "named") return explicit;
  if (typeof source.name === "string" && source.name) return scopeKindOf(source.name);
  const projectId = source.project_id ?? cfg?.project_id;
  if (typeof projectId === "string") {
    return projectId === WORKSPACE_GLOBAL_PROJECT_ID ? "global" : "project";
  }
  return null;
}

/**
 * Human-readable label for a per-project scope's identity: the basename of its
 * absolute `project_root` (e.g. `/Users/me/code/coffer` → `coffer`), or `null`
 * when the root is unknown. Surfaces render `projectDirName(project_root) ??
 * name` so a project scope reads as e.g. "coffer" with the full path as a
 * secondary detail, instead of the opaque `project-<ULID>` resource name.
 * Handles POSIX and Windows separators and trailing slashes.
 */
export function projectDirName(projectRoot?: string | null): string | null {
  if (!projectRoot) return null;
  const trimmed = projectRoot.replace(/[/\\]+$/, "");
  const parts = trimmed.split(/[/\\]/);
  const base = parts[parts.length - 1];
  return base || null;
}

/**
 * The scope's readable display name: a user-set `label` wins, else the
 * `project_root` basename, else the already-readable `name` of a global scope
 * or a named collection. Returns `null` only for a project scope with neither a
 * label nor a known root (an "orphan") — the caller shows a graceful
 * placeholder rather than the opaque `project-<ULID>` resource name.
 */
export function scopeDisplayName(scope: {
  label?: string | null;
  project_root?: string | null;
  scope?: ScopeKind;
  name: string;
}): string | null {
  if (scope.label) return scope.label;
  const basename = projectDirName(scope.project_root);
  if (basename) return basename;
  const kind = scope.scope ?? scopeKindOf(scope.name);
  if (kind === "project") return null;
  return scope.name;
}

/**
 * Per-scope settings. There are NO embedding fields: embedding is an
 * installation-wide setting (Settings → Embedding), and a scope opts into
 * semantic search purely by listing `vector` in `retrieval_modes`.
 */
export interface KnowledgeConfigOut {
  retrieval_modes: RetrievalMode[];
  default_mode: RetrievalMode;
  /** Bound on one written entry. */
  max_entry_chars: number;
  chunk_size: number;
  chunk_overlap: number;
  max_document_bytes: number;
  /** Re-ingest documents whose tracked external source file changed. */
  auto_update_sources: boolean;
  /** Project ids merged INTO this scope (system-managed, never user-set). */
  merged_identities?: string[];
}

/** The mutable subset of the config; the PATCH merges, so send only changes. */
export type KnowledgeConfigPatch = Partial<Omit<KnowledgeConfigOut, "merged_identities">>;

export interface ScopeOut {
  ref: string;
  kind: string;
  name: string;
  scope: ScopeKind;
  project_id: string;
  /** Absolute git root of a project scope; null for global / named. */
  project_root?: string | null;
  /** User-set display label; takes precedence over the derived basename. */
  label?: string | null;
  description: string | null;
  config: KnowledgeConfigOut;
  enabled: boolean;
  /** Absolute on-disk directory holding this scope's markdown. */
  scope_dir?: string;
  /** Entries written into the `knowledge/` lane. */
  entry_count?: number;
  /** Documents ingested into `inbox/` — a DIFFERENT lane, never summed. */
  document_count?: number;
  created_at: string;
  updated_at: string;
}

export interface ScopeListOut {
  scopes: ScopeOut[];
}

export interface ScopeMetrics {
  entry_count: number;
  document_count: number;
  chunk_count: number;
  /** Documents indexed keyword-only because the embedder was unavailable. */
  documents_degraded: number;
  indexed_modes: RetrievalMode[];
  disk_bytes: number;
}

export interface EntryOut {
  id: string;
  scope_name: string;
  scope: ScopeKind;
  title: string;
  description: string;
  text: string;
  actor: KnowledgeActor;
  origin_session_id?: string | null;
  /** Absolute on-disk path of the entry's Markdown file (FileActions). */
  path?: string;
  /** Absolute on-disk path of the entry file's containing folder. */
  folder_path?: string;
  created_at: string;
  updated_at: string;
}

export interface EntryListOut {
  entries: EntryOut[];
  total: number;
}

export interface EntryInput {
  text: string;
  title?: string | null;
  description?: string | null;
}

export interface RecallHit {
  id: string;
  text: string;
  score: number;
  source: string;
  time: string;
}

export interface RecallResponse {
  // External retrieval is "one query → one answer": the backend auto-selects
  // the strategy, so the response carries only ranked hits — no `mode`,
  // no `fallback`.
  hits: RecallHit[];
}

// --- lane read views --------------------------------------------------------
// Beyond entries and documents a scope carries curated lanes: Rules (a single
// doc), Handoff (per-branch scene notes) and the consolidation Changelog. All
// are agent-authored and rendered through the unified file preview.

/** Rules lane: a single curated doc; `text` is null when the scope has none. */
export interface RulesOut {
  text: string | null;
}

/** One handoff scene note (`handoff/<branch-slug>.md`). */
export interface HandoffSceneOut {
  branch: string;
  text: string;
  /** ISO date-time the scene was last written. */
  updated_at: string;
  path: string;
  folder_path: string;
}

/** Handoff lane: per-branch scene notes; empty scope → `scenes:[]`. */
export interface HandoffOut {
  scenes: HandoffSceneOut[];
}

/** Changelog lane: the consolidation log; `text` is null when absent. */
export interface ConsolidationLogOut {
  text: string | null;
  path: string;
  folder_path: string;
}

// AI-assisted scope merge wire types live in ./merge-types (250-line limit).
export * from "./merge-types";
