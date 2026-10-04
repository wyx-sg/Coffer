// src/lib/hooks/useUsage.ts — the queries and mutation of Model providers › Usage: the metered summary.
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { usageSummaryKey } from "@/lib/api/queryKeys";
import { fetchUsageSummary, type UsageQuery } from "@/lib/api/usage";

/** The summary for one range + grouping. The previous answer stays on screen
 *  while a new range loads, so switching ranges does not flash skeletons. */
export function useUsageSummary(q: UsageQuery) {
  return useQuery({
    queryKey: usageSummaryKey({ ...q }),
    queryFn: () => fetchUsageSummary(q),
    placeholderData: keepPreviousData,
  });
}
