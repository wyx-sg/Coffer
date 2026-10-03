// frontend/src/lib/reach/useBulkApply.ts
//
// Writes a bulk reach plan to every selected item and reports what landed, per
// item. Every item is attempted (allSettled), so one failure never aborts the
// rest; the result carries the failures so the popover can show them in place
// — a bulk reach never toasts a failure. Lists refresh once, afterwards.
import { useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { agentsKey, resourcesKey, scopeKey } from "@/lib/api/queryKeys";
import { resourcesApi } from "@/lib/api/resources";
import { putScopeChecked } from "@/lib/reach/deliveryFailure";
import type { BulkRow } from "@/lib/reach/bulkReach";
import type { ReachValue } from "@/lib/reach/useReachWrites";
import { sameScope } from "@/lib/scope";

/** One item and the reach it should end up with. */
export interface BulkWrite {
  row: BulkRow;
  value: ReachValue;
}

export interface BulkFailure {
  write: BulkWrite;
  message: string;
}

export function useBulkApply(invalidate: QueryKey[] = []) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [pending, setPending] = useState(false);

  const apply = useCallback(
    async (writes: BulkWrite[]): Promise<{ ok: number; failures: BulkFailure[] }> => {
      setPending(true);
      try {
        const results = await Promise.allSettled(
          writes.map(async ({ row, value }) => {
            // Off leaves the scope untouched; the other two enable, then set it.
            if (!value.enabled) return void (await resourcesApi.disable(row.uid));
            if (!row.enabled) await resourcesApi.enable(row.uid);
            if (!sameScope(row.scope ?? null, value.scope)) {
              await putScopeChecked(row.uid, value.scope);
            }
          }),
        );
        const failures = results.flatMap((r, i) =>
          r.status === "rejected"
            ? [{ write: writes[i] as BulkWrite, message: translateApiError(t, r.reason) }]
            : [],
        );
        for (const key of [resourcesKey, scopeKey, agentsKey, ...invalidate]) {
          void qc.invalidateQueries({ queryKey: key });
        }
        return { ok: writes.length - failures.length, failures };
      } finally {
        setPending(false);
      }
    },
    [t, qc, invalidate],
  );
  return { apply, isPending: pending };
}
