// src/components/usage/UsageTab.tsx — Model providers › Usage: the API-key requests Coffer's proxy metered, over a range.
//
// Tiles, a cost-per-day chart and a breakdown by model, agent or day. The
// range, the Agent and Provider filters and the breakdown live in the URL
// (`?range=`, `?agent=`, `?provider=`, `?by=`, beside the page's `?tab=usage`)
// so a refresh or Back keeps them. Before any API-key usage exists the tab is only its empty
// state, with no controls to narrow nothing; an empty range after that says
// only the range is empty. The data is Coffer's own, so there is no Refresh.
import { BarChart3 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { FilterPill, FilterRow, TimeRangePill } from "@/components/filters";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { agentTypeLabel } from "@/lib/agents/display";
import type { UsageQuery } from "@/lib/api/usage";
import { useAgents } from "@/lib/hooks/useAgents";
import { useProviders } from "@/lib/hooks/useProviders";
import { useUsageSummary } from "@/lib/hooks/useUsage";
import { formatDay } from "@/lib/usage/format";
import {
  GROUPINGS,
  PRESET_RANGES,
  addDays,
  localDay,
  parseDay,
  rangeOf,
  rangeValue,
  readUsageQuery,
  writeUsageQuery,
} from "@/lib/usage/range";
import { BreakdownTable } from "./BreakdownTable";
import { CostChart } from "./CostChart";
import { UsageTiles } from "./UsageTiles";

/** Daily totals are kept this long: nothing in it means nothing ever went through the proxy. */
const DAILY_TOTALS_DAYS = 365;

interface Props {
  /** Switch the page to its Providers tab ("Open Providers"). */
  onOpenProviders: () => void;
}

export function UsageTab({ onOpenProviders }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [params, setParams] = useSearchParams();
  const query = readUsageQuery(params);
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
  const providers = useProviders();
  const agents = useAgents();

  const setQuery = (next: UsageQuery) =>
    setParams(writeUsageQuery(params, next), { replace: true });
  const presets = PRESET_RANGES.map((id) => ({ id, label: t(`usage.presets.${id}`) }));
  const agentTypes = [...new Set((agents.data ?? []).map((a) => a.type))];
  const proxied = (providers.data ?? []).filter((p) => !p.local_runtime);
  const filtered = !!query.agent_type || !!query.connection_uid;
  const data = summary.data;
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

  if (ever.isLoading) {
    return <Skeleton className="h-48 w-full rounded-xl" data-testid="usage-loading" />;
  }
  if (ever.data?.totals.requests === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title={t("usage.empty.firstTitle")}
        description={t("usage.empty.firstBody")}
        secondaryAction={
          <Button variant="outline" onClick={onOpenProviders}>
            {t("usage.empty.openProviders")}
          </Button>
        }
        className="pt-16"
      />
    );
  }

  const rangeLabel =
    query.range === "custom" && query.from && query.to
      ? `${formatDay(parseDay(query.from), lang, "month")} – ${formatDay(parseDay(query.to), lang, "month")}`
      : t(`usage.range.${query.range}`);

  const body = (() => {
    if (summary.isLoading) {
      return <Skeleton className="h-48 w-full rounded-xl" data-testid="usage-loading" />;
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
          icon={BarChart3}
          title={t("usage.empty.rangeTitle")}
          description={t("usage.empty.rangeBody")}
          className="rounded-xl border border-border bg-surface-raised"
        />
      );
    }
    return (
      <>
        <UsageTiles totals={data.totals} priceNote={data.price_note} unpriced={unpriced} />
        {byDay.data ? (
          <CostChart byDay={byDay.data} />
        ) : byDay.isError ? (
          <p className="text-xs text-text-muted">{t("usage.chart.error")}</p>
        ) : (
          <Skeleton className="h-36 w-full" />
        )}
        <div className="flex flex-col gap-3">
          <Segmented
            label={t("usage.table.breakdown")}
            value={query.group_by}
            options={GROUPINGS.map((g) => ({ value: g, label: t(`usage.table.by.${g}`) }))}
            onChange={(g) => setQuery({ ...query, group_by: g })}
            className="self-start"
          />
          <BreakdownTable summary={data} totalLabel={rangeLabel} />
        </div>
      </>
    );
  })();

  return (
    <div className="flex flex-col gap-5">
      <FilterRow
        active={filtered}
        onClear={() => setQuery({ ...query, agent_type: undefined, connection_uid: undefined })}
      >
        <TimeRangePill
          dateOnly
          value={rangeValue(query)}
          presets={presets}
          onChange={(v) => setQuery({ ...query, from: undefined, to: undefined, ...rangeOf(v) })}
        />
        <FilterPill
          mode="single"
          label={t("usage.filters.agent")}
          options={agentTypes.map((a) => ({ value: a, label: agentTypeLabel(a) }))}
          value={query.agent_type ?? null}
          onChange={(a) => setQuery({ ...query, agent_type: a ?? undefined })}
        />
        <FilterPill
          mode="single"
          label={t("usage.filters.provider")}
          options={proxied.map((p) => ({ value: p.uid, label: p.title || p.name }))}
          value={query.connection_uid ?? null}
          onChange={(p) => setQuery({ ...query, connection_uid: p ?? undefined })}
          searchPlaceholder={t("usage.filters.findProvider")}
        />
      </FilterRow>
      {body}
    </div>
  );
}
