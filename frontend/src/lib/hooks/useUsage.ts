// src/lib/hooks/useUsage.ts — every query and mutation of the Usage page: the metered summary and its CSV export.
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { usageSummaryKey } from "@/lib/api/queryKeys";
import { fetchUsageCsv, fetchUsageSummary, type UsageQuery } from "@/lib/api/usage";
import { saveFile } from "@/lib/activity/export";

/** The summary for one range + grouping. The previous answer stays on screen
 *  while a new range loads, so switching ranges does not flash skeletons. */
export function useUsageSummary(q: UsageQuery) {
  return useQuery({
    queryKey: usageSummaryKey({ ...q }),
    queryFn: () => fetchUsageSummary(q),
    placeholderData: keepPreviousData,
  });
}

/** Download the summary for the current range and grouping as CSV. */
export function useExportUsageCsv() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: async (q: UsageQuery) => {
      const csv = await fetchUsageCsv(q);
      const span = q.range === "custom" ? `${q.from ?? ""}_${q.to ?? ""}` : q.range;
      saveFile(`coffer-usage-${span}-${q.group_by}.csv`, "text/csv", csv);
    },
    onError: (e) => toast.error(translateApiError(t, e)),
  });
}
