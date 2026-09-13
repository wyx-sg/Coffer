// frontend/src/kinds/memory/types.ts
//
// Wire types for the `memory` kind. Memory is Coffer's read-only aggregation
// of the agents' own native memories, normalised into facts partitioned by
// project (plus `global`) — see docs/decisions/aggregate-agent-memory-never-write-it.md
// and specs/memory/spec.md. Coffer never writes an agent's native memory; a
// fact's ONLY non-derived state is the developer's own overrides (FR-040).
//
// The memory routes are not in the mcp-gateway OpenAPI contract that
// `npm run codegen` reads, so these are hand-written, mirroring
// `kinds/knowledge/types.ts`. Field names match
// `backend/coffer/surfaces/http/memory/schemas.py` exactly.

/** One partition: a project's slug, or `global` for facts about the person. */
export interface PartitionOut {
  name: string;
  /** Absolute project root this partition was named from; empty for `global`. */
  project_root: string;
  fact_count: number;
}

export interface PartitionListOut {
  partitions: PartitionOut[];
}

/** Where one fact came from: which agent, which native file, when. */
export interface OriginOut {
  agent: string;
  /** Absolute path of the agent's own native memory file. */
  native_path: string;
  /** The fact's anchor within that file (stable across recomputation). */
  anchor: string;
  /** When Coffer's own aggregation captured this fact. */
  captured_at: string;
  /** The source's own timestamp, when it has one; empty otherwise. */
  source_written_at: string;
}

export type MemoryFactType = "user" | "feedback" | "project";
export type MemoryFactStatus = "active" | "superseded";

/** One fact without its body/origins — the shape `list_facts` returns. */
export interface FactSummaryOut {
  /** Stable identity across recomputation (FR-022); what overrides key on. */
  key: string;
  /** Short, URL-safe identity within its partition — `GET .../facts/{slug}`. */
  slug: string;
  partition: string;
  title: string;
  description: string;
  type: MemoryFactType;
  status: MemoryFactStatus;
  /** Non-empty names the fact key this one was superseded by. */
  superseded_by: string;
  /** Fact keys this one is flagged as disagreeing with. */
  conflicts_with: string[];
  /** True when a supersession/conflict here is the model's finding rather
   *  than something the developer settled (FR-033). */
  proposed: boolean;
  /** The developer's own decision, stamped on from the overrides table —
   *  not a property of the derived fact itself. */
  hidden: boolean;
  pinned: boolean;
}

export interface FactListOut {
  facts: FactSummaryOut[];
}

/** One fact's full detail: its own words (never a paraphrase) plus origins. */
export interface FactOut extends FactSummaryOut {
  body: string;
  origins: OriginOut[];
}

export interface AggregationResultOut {
  partitions: string[];
  facts_written: number;
  sources_read: number;
  sources_skipped: number;
  /** Native source paths that failed to parse (FR-005) — the other agent's
   *  aggregation still completed. */
  failures: string[];
}

export interface OrganiseResultOut {
  partition: string;
  merged: number;
  superseded: number;
  conflicts: number;
  model_used: boolean;
}

/** The developer's decisions about one fact (FR-040). Every field defaults
 *  to "no decision of this kind". */
export interface OverrideOut {
  fact_key: string;
  hidden: boolean;
  pinned: boolean;
  /** Non-empty: the fact key the developer settled this one as superseded by. */
  superseded_by: string;
  /** Non-empty: the fact key the developer settled a conflict in favour of. */
  conflict_choice: string;
}

export interface OverrideListOut {
  overrides: OverrideOut[];
}

/** The one field a PATCH may set at a time — every other field is left as-is. */
export type OverrideField = "hidden" | "pinned" | "superseded_by" | "conflict_choice";

/** Partial update to one fact's override; only the named fields are applied. */
export interface OverridePatch {
  hidden?: boolean;
  pinned?: boolean;
  superseded_by?: string;
  conflict_choice?: string;
}

/** Per-agent delivery state (FR-055) — the point of this feature: whether
 *  installed is not "success", `last_fired_at` is. */
export interface DeliveryStatusOut {
  agent: string;
  installed: boolean;
  /** Coffer's own CLI invocation the hook runs. */
  command: string;
  /** Empty string: installed (or not) but never actually fired. */
  last_fired_at: string;
  /** The hook event delivery is attached to (e.g. `SessionStart`). */
  event: string;
}

export interface DeliveryStatusListOut {
  delivery: DeliveryStatusOut[];
}
