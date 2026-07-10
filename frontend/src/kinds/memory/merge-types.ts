// frontend/src/kinds/memory/merge-types.ts
//
// Wire types for the AI-assisted store merge (spec 007 amendment 2026-07-10).
// Split from types.ts (frontend 250-line file limit); re-exported there so
// `import { … } from "./types"` / `"./api"` call sites see one surface.
// `POST /memory_stores/merge_scan` proposes same-project pairs (deterministic
// same-remote tier + internal-engine verdicts); `POST /memory_stores/merge`
// consolidates one confirmed pair additively and retires the source.

/** What the scan knew about one store when it judged the pair. */
export interface StoreEvidenceOut {
  store: string;
  label: string | null;
  root: string | null;
  remote: string | null;
  facts: number;
}

/** One scan proposal: merge `source` away into `target`. */
export interface MergeProposalOut {
  source: string;
  target: string;
  /** `certain` (deterministic) | `high` | `medium` | `low` (engine). */
  confidence: string;
  /** `remote` = proved by matching origin remote; `engine` = LLM verdict. */
  judged_by: string;
  reason: string;
  source_evidence: StoreEvidenceOut;
  target_evidence: StoreEvidenceOut;
}

/** Scan response; `engine: "no_model"` = deterministic proposals only. */
export interface MergeScanOut {
  engine: string;
  truncated: boolean;
  proposals: MergeProposalOut[];
}

/** Merge outcome; `reorg_status` reports the FR-059 post-merge organize. */
export interface MergeOut {
  target: string;
  merged_files: number;
  label_moved: boolean;
  root_moved: boolean;
  aliases: string[];
  reorg_status: string;
}

