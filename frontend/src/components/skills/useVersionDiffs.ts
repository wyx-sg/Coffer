// frontend/src/components/skills/useVersionDiffs.ts
// The diffs a skill's History needs, as change-preview items: what each chosen
// version did to each file it touched, or — for Restore — what putting an older
// version back would undo. A version never changes, so each diff is read once.
import { useQueries } from "@tanstack/react-query";

import type { ChangeItem, ChangeOp } from "@/lib/changePreview/changeCounts";
import { vaultDiffKey } from "@/lib/api/queryKeys";
import { vaultApi, type VaultDiffOut } from "@/lib/api/vault";
import { parseUnifiedDiff } from "./skillSourceHelpers";

export interface DiffRequest {
  /** Vault-relative path of the file. */
  path: string;
  /** The version whose change to that file is read. */
  version: string;
}

export function useVersionDiffs(requests: readonly DiffRequest[]) {
  const results = useQueries({
    queries: requests.map((r) => ({
      queryKey: vaultDiffKey(r.path, r.version),
      queryFn: () => vaultApi.diff(r.path, r.version),
      staleTime: Infinity,
    })),
  });
  return {
    pending: results.some((r) => r.isPending),
    error: results.find((r) => r.error)?.error ?? null,
    diffs: results.map((r) => r.data as VaultDiffOut | undefined),
  };
}

const STATUS_OP: Record<string, ChangeOp> = {
  added: "add",
  removed: "remove",
  modified: "modify",
};

/** One change-preview item for a file's diff in a version. */
export function diffItem(id: string, path: string, status: string, diff: VaultDiffOut): ChangeItem {
  return {
    id,
    agentType: "coffer",
    path,
    op: STATUS_OP[status] ?? "modify",
    added: diff.added,
    removed: diff.removed,
    diff: parseUnifiedDiff(diff.diff),
  };
}
