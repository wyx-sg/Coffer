// src/components/usage/UsageSection.tsx — "API-key providers": the metered requests of a range as tiles, a cost chart and a breakdown.
//
// Loads and fails on its own (quota trouble never blanks it). The breakdown
// tab is the summary's grouping and lives in the URL with the range.
import { Info, KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { UsageQuery, UsageSummary } from "@/lib/api/usage";
import { formatDay } from "@/lib/usage/format";
import { GROUPINGS, parseDay } from "@/lib/usage/range";
import { BreakdownTable } from "./BreakdownTable";
import { CostChart } from "./CostChart";
import { RangeControl } from "./RangeControl";
import { UsageTiles } from "./UsageTiles";

/** A query's state as the section needs it. */
interface Loaded<T> {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  refetch: () => unknown;
}

interface Props {
  query: UsageQuery;
  onQueryChange: (next: UsageQuery) => void;
  detailDays: number | null;
  /** The summary in the page's grouping (tiles, table). */
  summary: Loaded<UsageSummary>;
  /** The same range by day (the chart). */
  byDay: Loaded<UsageSummary>;
  /** Some agent has reported quota — so "nothing yet" would be wrong for the page as a whole. */
  hasQuota: boolean;
}

export function UsageSection({
  query,
  onQueryChange,
  detailDays,
  summary,
  byDay,
  hasQuota,
}: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const rangeLabel =
    query.range === "custom" && query.from && query.to
      ? `${formatDay(parseDay(query.from), lang, "long")} – ${formatDay(parseDay(query.to), lang, "long")}`
      : t(`usage.providers.range.${query.range}`);
  const data = summary.data;
  const providersLink = (
    <Button asChild size="sm">
      <Link to="/model-providers">{t("usage.empty.openProviders")}</Link>
    </Button>
  );

  const body = (() => {
    if (summary.isLoading) {
      return <Skeleton className="h-48 w-full rounded-xl" data-testid="usage-loading" />;
    }
    if (summary.isError || !data) {
      return (
        <EmptyState
          tone="error"
          title={t("usage.providers.error")}
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
      return hasQuota ? (
        <EmptyState
          icon={KeyRound}
          title={t("usage.empty.rangeTitle")}
          description={t("usage.empty.rangeBody")}
          className="rounded-xl border border-border bg-surface-raised"
        />
      ) : (
        <EmptyState
          icon={KeyRound}
          title={t("usage.empty.firstTitle")}
          description={t("usage.empty.firstBody")}
          action={providersLink}
          className="rounded-xl border border-border bg-surface-raised"
        />
      );
    }
    return (
      <>
        <div className="overflow-hidden rounded-xl border border-border bg-surface-raised">
          <div className="grid grid-cols-1 gap-8 p-4 lg:grid-cols-[300px_minmax(0,1fr)]">
            <UsageTiles totals={data.totals} />
            {byDay.data ? (
              <CostChart byDay={byDay.data} />
            ) : byDay.isError ? (
              <p className="text-xs text-text-muted">{t("usage.chart.error")}</p>
            ) : (
              <Skeleton className="h-36 w-full" />
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-border-subtle bg-surface-footer px-4 py-2.5 text-xs text-text-muted">
            <Info className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
            {/* The daemon's own note on which prices costed this range (server copy). */}
            <span>{data.price_note}</span>
            <Link
              to="/model-providers"
              className="ml-auto whitespace-nowrap font-label text-accent-text hover:underline"
            >
              {t("usage.editPrices")}
            </Link>
          </div>
        </div>
        <Tabs
          value={query.group_by}
          onValueChange={(v) => onQueryChange({ ...query, group_by: v as UsageQuery["group_by"] })}
          className="mt-2"
        >
          <TabsList aria-label={t("usage.table.breakdown")}>
            {GROUPINGS.map((g) => (
              <TabsTrigger key={g} value={g}>
                {t(`usage.table.by.${g}`)}
              </TabsTrigger>
            ))}
          </TabsList>
          {GROUPINGS.map((g) => (
            <TabsContent key={g} value={g} className="mt-1">
              <BreakdownTable summary={data} totalLabel={rangeLabel} />
            </TabsContent>
          ))}
        </Tabs>
      </>
    );
  })();

  return (
    <section aria-label={t("usage.providers.title")} className="flex flex-col gap-2">
      <div className="flex min-h-7 flex-wrap items-center gap-x-2 gap-y-2.5">
        <h2 className="text-sm font-semibold text-text">{t("usage.providers.title")}</h2>
        <span className="text-xs text-text-muted">{t("usage.providers.subtitle")}</span>
        <div className="basis-full">
          <RangeControl query={query} detailDays={detailDays} onChange={onQueryChange} />
        </div>
      </div>
      {body}
    </section>
  );
}
