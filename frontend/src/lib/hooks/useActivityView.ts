// src/lib/hooks/useActivityView.ts — what the Activity page is looking at: the tab, every filter (all in the URL) and the open record.
//
// The URL carries the tab (`?tab=`, Everything by default) and each filter —
// `q` the search, `range` the time range, `by`, `kind` (comma-joined), `status`,
// `level`, `logger` — so a link can land on the daemon log, "View in Activity"
// can arrive already searching a name, and a reload comes back where it was.
// A key at its default is left out. Until the reader picks a time range each
// tab opens on its own — the last hour, and the last 24 hours on the Daemon
// log, whose records are far sparser. Moving to another tab closes the open
// record and keeps the search, the range and who; the tab's own filters (kind,
// status, level, logger) do not carry over. A move can also carry filters, so
// "Show the MCP call" lands on MCP calls already looking for it.
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  DEFAULT_FILTERS,
  defaultRange,
  type ActivityFilters,
  type StatusFilter,
} from "@/lib/activity/filters";
import { ACTIVITY_TABS, type ActivityTab } from "@/lib/activity/records";
import { normalizeRange, rangeParam } from "@/lib/filters/timeRangeValue";

/** The preset ids Activity's time range offers; a custom range is also valid. */
export const RANGE_PRESETS = ["1h", "24h", "7d", "30d"] as const;

const STATUSES: readonly StatusFilter[] = ["all", "ok", "failed"];
const LEVELS = ["info", "warning", "error"] as const;

function isActivityTab(value: string | null): value is ActivityTab {
  return (ACTIVITY_TABS as readonly string[]).includes(value ?? "");
}

function list(raw: string | null): string[] {
  return raw ? raw.split(",").filter(Boolean) : [];
}

/** The filters a URL holds, for the tab it names. */
function readFilters(params: URLSearchParams, tab: ActivityTab): ActivityFilters {
  const status = params.get("status") as StatusFilter | null;
  const level = params.get("level") as (typeof LEVELS)[number] | null;
  return {
    range: normalizeRange(params.get("range"), RANGE_PRESETS, defaultRange(tab)),
    search: params.get("q") ?? "",
    by: list(params.get("by")),
    kinds: list(params.get("kind")),
    status: status && STATUSES.includes(status) ? status : DEFAULT_FILTERS.status,
    level: level && LEVELS.includes(level) ? level : DEFAULT_FILTERS.level,
    logger: params.get("logger") || null,
  };
}

/** Write `filters` onto `params`, leaving out whatever is at its default. */
function writeFilters(params: URLSearchParams, filters: ActivityFilters, tab: ActivityTab): void {
  const set = (key: string, value: string | undefined) => {
    if (value) params.set(key, value);
    else params.delete(key);
  };
  set("range", rangeParam(filters.range, defaultRange(tab)));
  set("q", filters.search || undefined);
  set("by", filters.by.join(",") || undefined);
  set("kind", filters.kinds.join(",") || undefined);
  set("status", filters.status === DEFAULT_FILTERS.status ? undefined : filters.status);
  set("level", filters.level || undefined);
  set("logger", filters.logger ?? undefined);
}

export function useActivityView() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab: ActivityTab = isActivityTab(requested) ? requested : "everything";
  const query = params.toString();
  // Keyed on the query text: `params` is a fresh object every render.
  const filters = useMemo(() => readFilters(new URLSearchParams(query), tab), [query, tab]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const setTab = (next: string, patch: Partial<ActivityFilters> = {}) => {
    const nextTab: ActivityTab = isActivityTab(next) ? next : "everything";
    const search = new URLSearchParams(params);
    if (nextTab === "everything") search.delete("tab");
    else search.set("tab", nextTab);
    for (const key of ["kind", "status", "level", "logger"]) search.delete(key);
    // A range the reader never chose is the tab's own default, not a choice.
    const chosen = normalizeRange(params.get("range"), RANGE_PRESETS, "");
    writeFilters(
      search,
      { ...readFilters(search, nextTab), ...(chosen ? { range: chosen } : {}), ...patch },
      nextTab,
    );
    setParams(search, { replace: true });
    setSelectedKey(null);
  };

  const changeFilters = (next: ActivityFilters) => {
    const search = new URLSearchParams(params);
    writeFilters(search, next, tab);
    setParams(search, { replace: true });
  };

  // Clearing keeps the time range: it is the page's frame, not a filter.
  const clearFilters = () => changeFilters({ ...DEFAULT_FILTERS, range: filters.range });

  // The Daemon log toggles a row open in place; every other tab opens the drawer.
  const select = (key: string) =>
    setSelectedKey((current) => (tab === "daemon" && current === key ? null : key));

  return {
    tab,
    setTab,
    filters,
    changeFilters,
    clearFilters,
    selectedKey,
    setSelectedKey,
    select,
  };
}
