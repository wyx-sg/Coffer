// frontend/src/lib/hooks/useBulkRun.ts
// Runs one request per selected item, one after another, for the bulk bars of
// an agent's own items. Sequential because every request of a batch writes the
// same agent config files; it never stops at the first failure, so a batch
// always ends with a list of what went wrong (each failure carries its item and
// the translated reason). The lists refresh once, after the last request.
//
// Unlike useBulkMutate (concurrent, toasts a count) the caller reports: it
// knows the names, and a failed batch is offered again for just the failures.
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient, type QueryKey } from "@tanstack/react-query";

import { translateApiError } from "@/lib/api/errors";

/** @ui-only */
export interface BulkFailure<T> {
  item: T;
  message: string;
}

export function useBulkRun(invalidate: QueryKey[]) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [isPending, setPending] = useState(false);

  const run = useCallback(
    async <T>(items: readonly T[], runOne: (item: T) => Promise<unknown>) => {
      setPending(true);
      const failures: BulkFailure<T>[] = [];
      try {
        for (const item of items) {
          try {
            await runOne(item);
          } catch (error) {
            failures.push({ item, message: translateApiError(t, error) });
          }
        }
      } finally {
        setPending(false);
        for (const queryKey of invalidate) void qc.invalidateQueries({ queryKey });
      }
      return { ok: items.length - failures.length, failures };
    },
    [t, qc, invalidate],
  );

  return { run, isPending };
}
