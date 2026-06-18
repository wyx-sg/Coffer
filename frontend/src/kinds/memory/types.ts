// frontend/src/kinds/memory/types.ts
//
// Wire types + scope helpers for the redesigned `memory` kind (spec 007).
// Split out of api.ts to keep that file under the size limit; api.ts re-exports
// everything here so existing `import { … } from "./api"` call sites are
// unaffected.

export type RetrievalMode = "grep" | "keyword" | "vector";
export type Scope = "global" | "project";

/**
 * Who authored a memory fact. Mirrors the backend spec enum
 * `coffer.domain.memory.fact.Actor` (`Literal["agent", "user"]`, spec 007 FR-007):
 * a fact is written either by an agent at runtime or by the user through a
 * surface. This is the fact-authorship vocabulary — distinct from the broader
 * audit-log actor vocabulary (request origins `ui`/`cli`/`api` plus the domain
 * actors `user`/`agent`/`channel`/`system`) rendered via `audit.actor.*`.
 */
export type MemoryActor = "agent" | "user";

/**
 * Sentinel `project_id` used for installation-global resources (C01). A memory
 * store whose `project_id` equals this ULID is the global store; any other
 * value identifies a per-project store. Mirrors the backend's
 * `WORKSPACE_GLOBAL_PROJECT_ID`.
 */
export const WORKSPACE_GLOBAL_PROJECT_ID = "00000000000000000000000000";

/**
 * Derive a store's scope from the data the resource list actually returns.
 *
 * The generic `ResourceOut` rows in the resources list carry no top-level
 * `scope`; the truth lives on the store: an explicit `scope`, or — when only
 * `project_id` is exposed — whether that id is the WORKSPACE_GLOBAL sentinel.
 * Returns `null` when neither signal is present so callers can avoid silently
 * mislabeling a project store as "global".
 */
export function deriveScope(source: {
  scope?: unknown;
  project_id?: unknown;
  // `unknown` so any caller's config shape (the typed MemoryStoreConfigOut, a
  // generic ResourceOut config, a test fixture) is accepted; read defensively.
  config?: unknown;
}): Scope | null {
  const cfg = (source.config ?? undefined) as { scope?: unknown; project_id?: unknown } | undefined;
  const explicit = source.scope ?? cfg?.scope;
  if (explicit === "global" || explicit === "project") return explicit;
  const projectId = source.project_id ?? cfg?.project_id;
  if (typeof projectId === "string") {
    return projectId === WORKSPACE_GLOBAL_PROJECT_ID ? "global" : "project";
  }
  return null;
}

/**
 * Human-readable label for a per-project memory store's identity: the basename
 * of its absolute `project_root` (e.g. `/Users/me/code/coffer` → `coffer`), or
 * `null` when the root is unknown — the global store, or a project store
 * provisioned before its root was tracked. Surfaces render
 * `projectDirName(project_root) ?? name` so a per-project store reads as e.g.
 * "coffer" with the full path as a secondary detail, instead of the opaque
 * `project-<ULID>` store name (spec 007 FR-017a). Handles POSIX and Windows
 * separators and trailing slashes.
 */
export function projectDirName(projectRoot?: string | null): string | null {
  if (!projectRoot) return null;
  const trimmed = projectRoot.replace(/[/\\]+$/, "");
  const parts = trimmed.split(/[/\\]/);
  const base = parts[parts.length - 1];
  return base || null;
}

export interface MemoryStoreConfigOut {
  retrieval_modes: RetrievalMode[];
  default_mode: RetrievalMode;
  embedding_provider?: string | null;
  embedding_model?: string | null;
  embedding_base_url?: string | null;
  embedding_credential_ref?: string | null;
  embedding_dimensions: number;
  max_fact_chars: number;
}

export interface MemoryStoreOut {
  ref: string;
  kind: string;
  name: string;
  scope: Scope;
  project_id: string;
  // Absolute filesystem root of a project-scoped store, exposed by the backend
  // so a SYMLINK/RENDER projection can be anchored under that project. Absent
  // (null) for the global store and for project stores whose root is unknown.
  project_root?: string | null;
  description: string | null;
  config: MemoryStoreConfigOut;
  enabled: boolean;
  /** Number of facts in the store (shown in the stores table). */
  fact_count?: number;
  created_at: string;
  updated_at: string;
}

export interface MemoryStoreListOut {
  memory_stores: MemoryStoreOut[];
}

export interface MemoryStoreMetrics {
  fact_count: number;
  disk_bytes: number;
}

export interface FactOut {
  id: string;
  store_name: string;
  scope: Scope;
  name: string;
  description: string;
  text: string;
  type?: string | null;
  actor: MemoryActor;
  origin_session_id?: string | null;
  path?: string;
  created_at: string;
  updated_at: string;
}

export interface FactListOut {
  facts: FactOut[];
  total: number;
}

export interface RecallHit {
  id: string;
  text: string;
  score: number;
  source: string;
  time: string;
}

export interface RecallResponse {
  hits: RecallHit[];
  mode: RetrievalMode;
  fallback?: boolean;
}

export interface ProjectionOut {
  agent_ref: string;
  projection_mode: "SYMLINK" | "RENDER" | "NONE";
  target_path: string;
  native_memory_disabled: boolean;
  merged_existing?: boolean;
}

export interface ProjectionListOut {
  projections: ProjectionOut[];
}

export interface FactInput {
  text: string;
  name?: string | null;
  description?: string | null;
  type?: string | null;
}
