// src/lib/hooks/useUsage.ts — every query and mutation of the Usage page: the metered summary, its CSV export, subscription quota.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { usageKey, usageQuotaKey, usageSummaryKey } from "@/lib/api/queryKeys";
import {
  fetchUsageCsv,
  fetchUsageQuota,
  fetchUsageSummary,
  refreshUsageQuota,
  type QuotaList,
  type UsageQuery,
} from "@/lib/api/usage";
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

/** Each subscription agent's latest official windows. */
export function useUsageQuota() {
  return useQuery({ queryKey: usageQuotaKey, queryFn: fetchUsageQuota });
}

/**
 * Ask Codex's app-server for its windows now. The answer carries every
 * agent's latest quota, which replaces the cached list; a read that did not
 * happen comes back as `reason` and is rendered on the Codex card, so only a
 * transport failure toasts.
 */
export function useRefreshQuota() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: refreshUsageQuota,
    onSuccess: (out) => qc.setQueryData<QuotaList>(usageQuotaKey, { agents: out.agents }),
    onError: (e) => toast.error(translateApiError(t, e)),
  });
}

/** Re-read every usage query (the header's Refresh). */
export function useInvalidateUsage() {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: usageKey });
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
