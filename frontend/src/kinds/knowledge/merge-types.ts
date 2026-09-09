// frontend/src/kinds/knowledge/merge-types.ts
//
// Wire types for the AI-assisted scope merge. Split from types.ts (frontend
// 250-line file limit); re-exported there so `import { … } from "./types"` /
// `"./api"` call sites see one surface.
// `POST /knowledge/merge_scan` proposes same-project pairs (deterministic
// same-remote tier + internal-engine verdicts); `POST /knowledge/merge`
// consolidates one confirmed pair additively and retires the source.

/** What the scan knew about one scope when it judged the pair. */
export interface ScopeEvidenceOut {
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
  source_evidence: ScopeEvidenceOut;
  target_evidence: ScopeEvidenceOut;
}

/** Scan response; `engine: "no_model"` = deterministic proposals only. */
export interface MergeScanOut {
  engine: string;
  truncated: boolean;
  proposals: MergeProposalOut[];
}

/** Merge outcome; `reorg_status` reports the post-merge organize. */
export interface MergeOut {
  target: string;
  merged_files: number;
  label_moved: boolean;
  root_moved: boolean;
  aliases: string[];
  reorg_status: string;
}
