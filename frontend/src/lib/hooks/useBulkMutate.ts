// frontend/src/lib/hooks/useBulkMutate.ts
// Shared fan-out helper for the table bulk actions (delete / enable / disable /
// install / verify over the selected rows). Replaces the old per-call-site
// `await Promise.all(rows.map(mutate))` which rejected on the FIRST failure —
// leaving some rows changed, the dialog stuck, the selection uncleared, and no
// message. This runs every item with Promise.allSettled so one failure never
// aborts the rest, then surfaces a single summary toast ("N done, M failed")
// and runs one invalidation burst.
//
// Call sites pass the underlying API function as `runOne` (NOT a toasting
// mutation hook) so failures are summarised once here rather than producing one
// toast per failed row.
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";

import { useToast } from "@/components/ui/toast";

interface BulkOptions {
  /** Query keys to invalidate once after the batch settles (single burst). */
  invalidate?: (readonly unknown[])[];
}

/**
 * Returns `{ run, isPending }`. `run(items, runOne)` executes `runOne` for every
 * item concurrently, settling all of them, then:
 *   • toasts a per-result summary (success / partial / all-failed),
 *   • invalidates the configured query keys exactly once,
 *   • resolves with `{ ok, failed }` counts so the caller can decide whether to
 *     close a dialog / clear the selection.
 */
export function useBulkMutate(options: BulkOptions = {}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [isPending, setPending] = useState(false);
  const { invalidate } = options;

  const run = useCallback(
    async <T>(
      items: T[],
      runOne: (item: T) => Promise<unknown>,
    ): Promise<{ ok: number; failed: number }> => {
      setPending(true);
      try {
        const results = await Promise.allSettled(items.map((item) => runOne(item)));
        const failed = results.filter((r) => r.status === "rejected").length;
        const ok = results.length - failed;

        if (failed === 0) {
          toast.success(t("common.bulk.summary.allOk", { count: ok }));
        } else if (ok === 0) {
          toast.error(t("common.bulk.summary.allFailed", { count: failed }));
        } else {
          toast.error(t("common.bulk.summary.partial", { ok, failed }));
        }

        if (invalidate) {
          for (const key of invalidate) void qc.invalidateQueries({ queryKey: key });
        }
        return { ok, failed };
      } finally {
        setPending(false);
      }
    },
    [t, toast, qc, invalidate],
  );

  return { run, isPending };
}
