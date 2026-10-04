// src/lib/hooks/useActivityAnyRecords.ts — whether Coffer has recorded anything at all, in any of the three logs.
//
// The first run (design 6.2.09) is "no records at all", which is not the same
// as "none in the last hour": only the first hides the filter row and Export.
// Asked only when the tab shows nothing under no filter, one row's read of
// each log without a time window (the daemon log from warnings up, as Everything reads it).
import { useQuery } from "@tanstack/react-query";

import { fetchAuditPage, fetchCallPage, fetchDaemonPage } from "@/lib/api/activity";
import { activityAnyRecordsKey } from "@/lib/api/queryKeys";

/** True once any log holds a record, false when all are empty, undefined while unknown. */
export function useActivityAnyRecords(enabled: boolean): boolean | undefined {
  const query = useQuery({
    queryKey: activityAnyRecordsKey,
    enabled,
    queryFn: async ({ signal }) => {
      const [changes, calls, daemon] = await Promise.all([
        fetchAuditPage({}, 1, null, signal),
        fetchCallPage({}, 1, null, signal),
        fetchDaemonPage({ level: "warning" }, 1, null, signal),
      ]);
      return changes.entries.length + calls.invocations.length + daemon.records.length > 0;
    },
  });
  return query.data;
}
