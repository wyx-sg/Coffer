// src/pages/UsagePage.tsx — /usage: subscription quota as each agent reports it, and metered API-key usage over a range.
//
// Two sections that load and fail independently. The range and the breakdown
// live in the URL (`?range=`, `?from=&to=`, `?by=`) so a refresh or Back keeps
// them. Refresh re-reads the summary and asks Codex's app-server for fresh
// quota; the ⋯ menu exports the current range and grouping as CSV.
import { useState } from "react";
import { Gauge, RotateCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import { QuotaSection } from "@/components/usage/QuotaSection";
import { UsageSection } from "@/components/usage/UsageSection";
import { useRetentionPolicies } from "@/lib/hooks/useRetention";
import {
  useExportUsageCsv,
  useInvalidateUsage,
  useRefreshQuota,
  useUsageQuota,
  useUsageSummary,
} from "@/lib/hooks/useUsage";
import type { UsageQuery } from "@/lib/api/usage";
import { formatClock } from "@/lib/usage/format";
import { readUsageQuery, writeUsageQuery } from "@/lib/usage/range";

/** Per-request detail window when the retention policy has not loaded. */
const DEFAULT_DETAIL_DAYS = 30;

export function UsagePage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const query = readUsageQuery(params);
  const summary = useUsageSummary(query);
  const byDay = useUsageSummary({ ...query, group_by: "day" });
  const quota = useUsageQuota();
  const refresh = useRefreshQuota();
  const invalidate = useInvalidateUsage();
  const exportCsv = useExportUsageCsv();
  const retention = useRetentionPolicies();
  const [triedAt, setTriedAt] = useState<Date | null>(null);

  const policy = retention.data?.policies.find((p) => p.table_name === "mcp_invocations");
  const detailDays = policy ? policy.retention_days : DEFAULT_DETAIL_DAYS;
  const setQuery = (next: UsageQuery) => setParams(writeUsageQuery(params, next));
  const askCodex = () => {
    setTriedAt(new Date());
    refresh.mutate();
  };
  const updatedAt = Math.max(summary.dataUpdatedAt, quota.dataUpdatedAt);
  const now = new Date();
  const reason = refresh.data && !refresh.data.refreshed ? refresh.data.reason : null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        icon={Gauge}
        title={t("usage.title")}
        actions={
          <div className="flex items-center gap-2">
            {updatedAt > 0 ? (
              <span className="text-xs text-text-muted">
                {t("usage.updated", { time: formatClock(new Date(updatedAt), i18n.language) })}
              </span>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              disabled={refresh.isPending}
              onClick={() => {
                invalidate();
                askCodex();
              }}
            >
              <RotateCw aria-hidden />
              {t("usage.refresh")}
            </Button>
            <ActionMenu
              label={t("usage.more")}
              actions={[
                {
                  key: "export",
                  label: t("usage.exportCsv"),
                  disabled: exportCsv.isPending,
                  onSelect: () => exportCsv.mutate(query),
                },
              ]}
            />
          </div>
        }
      />
      <QuotaSection
        data={quota.data}
        isLoading={quota.isLoading}
        isError={quota.isError}
        onRetryLoad={() => void quota.refetch()}
        refresh={{ reason, triedAt, pending: refresh.isPending, onRetry: askCodex }}
        now={now}
      />
      <UsageSection
        query={query}
        onQueryChange={setQuery}
        detailDays={detailDays}
        summary={summary}
        byDay={byDay}
        hasQuota={!!quota.data?.agents.some((a) => a.has_value)}
      />
    </div>
  );
}
