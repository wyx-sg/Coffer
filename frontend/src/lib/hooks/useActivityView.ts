// src/lib/hooks/useActivityView.ts — what the Activity page is looking at: the tab (in the URL), the filters and the open record.
//
// The tab lives in the URL (`?tab=`, Everything by default), so a link can
// land on the daemon log and a reload comes back where it was. Until the
// reader picks a time window each tab opens on its own — the last hour, and
// the last 24 hours on the Daemon log, whose records are far sparser (design
// 6.1.09). Moving to another tab closes the open record; a move can also carry
// filters, so "Show the MCP call" lands on MCP calls already looking for it.
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { DEFAULT_FILTERS, type ActivityFilters } from "@/lib/activity/filters";
import { ACTIVITY_TABS, type ActivityTab } from "@/lib/activity/records";

function isActivityTab(value: string | null): value is ActivityTab {
  return (ACTIVITY_TABS as readonly string[]).includes(value ?? "");
}

/** The window a tab opens on until the reader picks one. */
function defaultWindow(tab: ActivityTab): string {
  return tab === "daemon" ? "24h" : DEFAULT_FILTERS.timeRange;
}

export function useActivityView() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab: ActivityTab = isActivityTab(requested) ? requested : "everything";
  const [filters, setFilters] = useState<ActivityFilters>(() => ({
    ...DEFAULT_FILTERS,
    timeRange: defaultWindow(tab),
  }));
  // Whether the reader chose the window; until then each tab opens on its own.
  const [windowChosen, setWindowChosen] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const setTab = (next: string, patch: Partial<ActivityFilters> = {}) => {
    const search = new URLSearchParams(params);
    if (next === "everything") search.delete("tab");
    else search.set("tab", next);
    setParams(search, { replace: true });
    setSelectedKey(null);
    const nextTab = isActivityTab(next) ? next : "everything";
    setFilters((f) => ({
      ...f,
      ...(windowChosen ? {} : { timeRange: defaultWindow(nextTab), from: "", to: "" }),
      ...patch,
    }));
  };

  const changeFilters = (next: ActivityFilters) => {
    if (
      next.timeRange !== filters.timeRange ||
      next.from !== filters.from ||
      next.to !== filters.to
    ) {
      setWindowChosen(true);
    }
    setFilters(next);
  };

  // Clearing keeps the time window: it is the page's frame, not a filter.
  const clearFilters = () =>
    setFilters({
      ...DEFAULT_FILTERS,
      timeRange: filters.timeRange,
      from: filters.from,
      to: filters.to,
    });

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
