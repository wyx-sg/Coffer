// src/components/usage/UsageTab.tsx — Model providers › Usage: what requests through API-key providers cost.
//
// Only metered API-key requests are shown (subscription logins never pass
// through Coffer). The range, the Agent and Provider filters and the breakdown
// live in the URL (`?range=`, `?from=&to=`, `?agent=`, `?provider=`, `?by=`) so a
// refresh or Back keeps them; "Export CSV" downloads exactly that. Before any
// usage exists the tab is only its empty state, without controls to narrow
// nothing; an empty range after that says only the range is empty.
import { Download, KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { agentTypeLabel } from "@/lib/agents/display";
import type { UsageQuery } from "@/lib/api/usage";
import { useAgents } from "@/lib/hooks/useAgents";
import { useProviders } from "@/lib/hooks/useProviders";
import { useRetentionPolicies } from "@/lib/hooks/useRetention";
import { useExportUsageCsv, useUsageSummary } from "@/lib/hooks/useUsage";
import { formatDay } from "@/lib/usage/format";
import {
  GROUPINGS,
  addDays,
  localDay,
  parseDay,
  readUsageQuery,
  writeUsageQuery,
} from "@/lib/usage/range";
import { BreakdownTable } from "./BreakdownTable";
import { CostChart } from "./CostChart";
import { RangePill } from "./RangePill";
import { UsagePill } from "./UsagePill";
import { UsageTiles } from "./UsageTiles";

/** Per-request detail window when the retention policy has not loaded. */
const DEFAULT_DETAIL_DAYS = 30;
/** Daily totals are kept this long: nothing in it means nothing ever went through the proxy. */
const DAILY_TOTALS_DAYS = 365;

export function UsageTab() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [params, setParams] = useSearchParams();
  const query = readUsageQuery(params);
  const setQuery = (next: UsageQuery) => setParams(writeUsageQuery(params, next));

  const summary = useUsageSummary(query);
  const byDay = useUsageSummary({ ...query, group_by: "day" });
  // Per model, whatever the breakdown: which models have no known price.
  const byModel = useUsageSummary({ ...query, group_by: "model" });
  // Whether anything ever went through the proxy: the first-run state.
  const today = new Date();
  const ever = useUsageSummary({
    range: "custom",
    from: localDay(addDays(today, 1 - DAILY_TOTALS_DAYS)),
    to: localDay(today),
    group_by: "agent",
  });
  const agents = useAgents();
  const providers = useProviders();
  const retention = useRetentionPolicies();
  const exportCsv = useExportUsageCsv();

  const policy = retention.data?.policies.find((p) => p.table_name === "mcp_invocations");
  const detailDays = policy ? policy.retention_days : DEFAULT_DETAIL_DAYS;
  const agentTypes = [...new Set((agents.data ?? []).map((a) => a.type))];
  const proxied = (providers.data ?? []).filter((p) => !p.local_runtime);

  const data = summary.data;
  const firstRun = ever.data?.totals.requests === 0 && !!data && data.totals.requests === 0;

  const unpricedRows = (byModel.data?.rows ?? []).filter(
    (r) => r.model && r.totals.unpriced_requests > 0,
  );
  const firstUnpriced = unpricedRows.find((r) => r.connection_uid) ?? unpricedRows[0];
  const unpriced = unpricedRows.length
    ? {
        count: unpricedRows.length,
        to: firstUnpriced?.connection_uid
          ? `/model-providers?provider=${encodeURIComponent(firstUnpriced.connection_uid)}&model=${encodeURIComponent(firstUnpriced.model ?? "")}`
          : "/model-providers",
      }
    : null;

  const totalRange =
    query.range === "custom" && query.from && query.to
      ? `${formatDay(parseDay(query.from), lang, "long")} – ${formatDay(parseDay(query.to), lang, "long")}`
      : t(`usage.table.totalRange.${query.range}`);

  if (firstRun) {
    return (
      <EmptyState
        icon={KeyRound}
        title={t("usage.empty.firstTitle")}
        description={t("usage.empty.firstBody")}
        action={
          <Button asChild variant="outline" size="sm">
            <Link to="/model-providers">{t("usage.empty.openProviders")}</Link>
          </Button>
        }
      />
    );
  }

  const body = (() => {
    if (summary.isLoading) {
      return <Skeleton className="h-64 w-full rounded-xl" data-testid="usage-loading" />;
    }
    if (summary.isError || !data) {
      return (
        <EmptyState
          tone="error"
          title={t("usage.error")}
          className="rounded-xl border border-border bg-surface-raised"
          action={
            <Button variant="outline" size="sm" onClick={() => void summary.refetch()}>
              {t("common.retry")}
            </Button>
          }
        />
      );
    }
    if (data.totals.requests === 0) {
      return (
        <EmptyState
          icon={KeyRound}
          title={t("usage.empty.rangeTitle")}
          description={t("usage.empty.rangeBody")}
          className="rounded-xl border border-border bg-surface-raised"
        />
      );
    }
    return (
      <>
        <UsageTiles totals={data.totals} unpriced={unpriced} />
        {byDay.data ? (
          <CostChart byDay={byDay.data} />
        ) : byDay.isError ? (
          <p className="text-xs text-text-muted">{t("usage.chart.error")}</p>
        ) : (
          <Skeleton className="h-44 w-full" />
        )}
        <div className="flex flex-col gap-3">
          <Segmented
            label={t("usage.table.breakdown")}
            value={query.group_by}
            options={GROUPINGS.map((g) => ({ value: g, label: t(`usage.table.by.${g}`) }))}
            onChange={(g) => setQuery({ ...query, group_by: g })}
            className="self-start"
          />
          <BreakdownTable summary={data} totalLabel={totalRange} />
        </div>
      </>
    );
  })();

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center gap-2">
        <RangePill query={query} detailDays={detailDays} onChange={setQuery} />
        <UsagePill
          label={t("usage.filters.agent")}
          allLabel={t("usage.filters.allAgents")}
          value={query.agent_type ?? ""}
          options={agentTypes.map((a) => ({ value: a, label: agentTypeLabel(a) }))}
          onChange={(a) => setQuery({ ...query, agent_type: a || undefined })}
        />
        <UsagePill
          label={t("usage.filters.provider")}
          allLabel={t("usage.filters.allProviders")}
          value={query.connection_uid ?? ""}
          options={proxied.map((p) => ({ value: p.uid, label: p.title || p.name }))}
          onChange={(p) => setQuery({ ...query, connection_uid: p || undefined })}
        />
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto"
          disabled={exportCsv.isPending}
          onClick={() => exportCsv.mutate(query)}
        >
          <Download aria-hidden />
          {t("usage.exportCsv")}
        </Button>
      </div>
      {body}
    </div>
  );
}
