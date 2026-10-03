// src/lib/hooks/useActivityFeed.ts — the visible Activity tab's records: the logs it reads, merged, filtered, held and counted.
//
// A tab reads one log (Changes, MCP calls, Daemon log) or all three
// (Everything). Each log is a `useActivitySource`; this hook decides each
// one's server-side filters from the tab's, merges what they loaded
// newest-first, applies the client-side half of the filters, and answers the
// questions the page asks: what to show, how many new records wait behind
// "↑ N new", how many records match in all, and whether older ones exist.
//
// Merging logs that page separately needs one rule to stay in order: a
// record is shown only if it is no older than the oldest record loaded from
// every log that still has older pages — otherwise loading an older page of
// one log could insert rows above others already on screen.
import { useMemo } from "react";
import type { TFunction } from "i18next";

import type { SourceParams } from "@/lib/api/activity";
import {
  mergeNewestFirst,
  recordLogger,
  recordTimeMs,
  type ActivityRecord,
  type ActivitySource,
  type ActivityTab,
} from "@/lib/activity/records";
import {
  matchesFilters,
  singleAgent,
  sourcesFor,
  totalsExact,
  type ActivityFilters,
  type FilterContext,
} from "@/lib/activity/filters";
import { eventTypesMatching } from "@/lib/activity/activityText";
import { resolveRange } from "@/lib/filters/timeRangeValue";
import { useActivitySource, type ActivitySourceState } from "./useActivitySource";

/** The Everything tab shows the daemon's warnings and errors, not its chatter. */
const EVERYTHING_DAEMON_FLOOR = "warning";

/** Each log's server-side filters for a tab. */
function sourceParams(
  source: ActivitySource,
  tab: ActivityTab,
  f: ActivityFilters,
  since: string | undefined,
  qTypes: string[],
): SourceParams {
  const q = f.search.trim() || undefined;
  // A change's kind is a category the audit route does not know (secrets,
  // sync, settings), so the kind filter is applied on the client.
  if (source === "change") return { source, params: { since, q, qTypes } };
  if (source === "call") {
    return {
      source,
      params: {
        since,
        status: tab === "mcp" && f.status !== "all" ? f.status : undefined,
        agentUid: singleAgent(tab, f),
        q,
      },
    };
  }
  return {
    source,
    params: { since, q, level: tab === "daemon" ? f.level : EVERYTHING_DAEMON_FLOOR },
  };
}

/** @ui-only What the page renders from the feed. */
export interface ActivityFeed {
  /** The rows to show, newest first, filtered. */
  rows: ActivityRecord[];
  /** New records waiting behind "↑ N new", filtered. */
  pendingCount: number;
  /** Whether anything waits at all, filtered out or not. */
  hasPending: boolean;
  releaseAll: () => void;
  /**
   * How many records match in all (a floor when the daemon log counted a
   * bounded tail), or undefined when a client-side filter makes the logs'
   * totals overcount or a total is not known yet.
   */
  total: { value: number; floor: boolean } | undefined;
  isLoading: boolean;
  /** The logs of this tab that failed to load. */
  failed: ActivitySourceState[];
  hasOlder: boolean;
  loadOlder: () => void;
  isLoadingOlder: boolean;
  /** Re-read the audit log's newest page now. */
  refreshChanges: () => void;
  /** The specs of the logs this tab reads, for the export. */
  specs: SourceParams[];
  /** The client-side predicate, for the export. */
  keep: (r: ActivityRecord) => boolean;
  /** The newest-first time window's upper bound, for display. */
  until: string | undefined;
  /** Every daemon logger among the loaded records, for the logger filter. */
  loggers: string[];
  /** The daemon log's file, when this tab reads it. */
  logPath: string | undefined;
}

interface Args {
  tab: ActivityTab;
  filters: ActivityFilters;
  t: TFunction;
  agentNames: ReadonlyMap<string, string>;
}

export function useActivityFeed({ tab, filters, t, agentNames }: Args): ActivityFeed {
  const { range } = filters;
  // Memoised: a rolling preset's `since` is computed from Date.now(), and it
  // is part of every query key — recomputing it per render would refetch
  // every keystroke.
  const { since, until } = useMemo(() => resolveRange(range), [range]);

  const active = useMemo(() => new Set(sourcesFor(tab, filters)), [tab, filters]);
  // The audit route searches the event code, the resource, the actor and the
  // details; the events whose localized sentence holds the text are named too.
  const qTypes = useMemo(() => eventTypesMatching(t, filters.search), [t, filters.search]);

  // The three logs are always the same three hooks; a log this tab does not
  // read is simply switched off.
  const changeSpec = sourceParams("change", tab, filters, since, qTypes);
  const callSpec = sourceParams("call", tab, filters, since, qTypes);
  const daemonSpec = sourceParams("daemon", tab, filters, since, qTypes);
  const change = useActivitySource(changeSpec, active.has("change"));
  const call = useActivitySource(callSpec, active.has("call"));
  const daemon = useActivitySource(daemonSpec, active.has("daemon"));

  const states = [change, call, daemon].filter((s) => active.has(s.source));
  const ctx: FilterContext = useMemo(() => ({ t, until, agentNames }), [t, until, agentNames]);
  const keep = useMemo(
    () => (r: ActivityRecord) => matchesFilters(r, tab, filters, ctx),
    [tab, filters, ctx],
  );

  // The oldest time every log with older pages has reached: nothing older
  // than it is shown until those logs are paged further.
  const frontier = Math.max(
    ...states.filter((s) => s.hasOlder && s.oldestAt !== undefined).map((s) => s.oldestAt ?? 0),
    0,
  );
  const merged = mergeNewestFirst(states.map((s) => s.records));
  const visible = frontier > 0 ? merged.filter((r) => recordTimeMs(r.at) >= frontier) : merged;
  const rows = visible.filter(keep);
  const pendingCount = states.reduce((n, s) => n + s.pending.filter(keep).length, 0);

  // The frontier logs are the ones to page: loading an older page of any
  // other would only fetch rows still hidden behind the frontier.
  // "of M": the logs' own totals, while they still describe what is shown.
  const totals = states.map((s) => s.total);
  const total =
    totalsExact(filters, tab) && states.length > 0 && totals.every((n) => n !== undefined)
      ? {
          value: totals.reduce<number>((n, x) => n + (x ?? 0), 0),
          floor: states.some((s) => s.capped),
        }
      : undefined;
  const pageable = states.filter((s) => s.hasOlder);
  const limiting = pageable.filter((s) => (s.oldestAt ?? 0) >= frontier);

  return {
    rows,
    pendingCount,
    hasPending: states.some((s) => s.pending.length > 0),
    releaseAll: () => states.forEach((s) => s.release()),
    total,
    isLoading: states.some((s) => s.isLoading),
    failed: states.filter((s) => s.error),
    hasOlder: pageable.length > 0,
    loadOlder: () => (limiting.length ? limiting : pageable).forEach((s) => s.loadOlder()),
    isLoadingOlder: states.some((s) => s.isLoadingOlder),
    refreshChanges: change.refreshHead,
    specs: [changeSpec, callSpec, daemonSpec].filter((s) => active.has(s.source)),
    keep,
    until,
    loggers: [...new Set(merged.map(recordLogger).filter(Boolean))].sort(),
    logPath: active.has("daemon") ? daemon.path : undefined,
  };
}
