// src/lib/hooks/useActivityFeed.ts — the visible Activity tab's records: the logs it reads, merged, filtered, held and counted.
//
// A tab reads one log (Changes, MCP calls, Daemon log) or all three
// (Everything). Each log is a `useActivitySource`; this hook decides each
// one's server-side filters from the tab's, merges what they loaded
// newest-first, applies the client-side half of the filters, and answers the
// questions the page asks: what to show, how many new records wait behind
// "↑ N new", how many records each tab holds, and whether older ones exist.
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
  sourcesFor,
  type ActivityFilters,
  type FilterContext,
} from "@/lib/activity/filters";
import { resolveTimeWindow } from "@/lib/timeRange";
import {
  useActivityCount,
  useActivitySource,
  type ActivityCount,
  type ActivitySourceState,
} from "./useActivitySource";

const CALL_STATUSES = ["ok", "error", "timeout", "denied"] as const;
type CallStatus = (typeof CALL_STATUSES)[number];

function isCallStatus(value: string): value is CallStatus {
  return (CALL_STATUSES as readonly string[]).includes(value);
}

/** The Everything tab shows the daemon's warnings and errors, not its chatter. */
const EVERYTHING_DAEMON_FLOOR = "warning";

/** Each log's server-side filters for a tab. */
function sourceParams(
  source: ActivitySource,
  tab: ActivityTab,
  f: ActivityFilters,
  since: string | undefined,
): SourceParams {
  if (source === "change") {
    const kind = f.kind.startsWith("change:") ? f.kind.slice("change:".length) : undefined;
    return {
      source,
      params: { since, kind: tab === "everything" || tab === "changes" ? kind : undefined },
    };
  }
  if (source === "call") {
    return {
      source,
      params: {
        since,
        uid: f.server !== "any" ? f.server : undefined,
        status: tab === "mcp" && isCallStatus(f.status) ? f.status : undefined,
        agentUid: f.by.startsWith("agent:") ? f.by.slice("agent:".length) : undefined,
      },
    };
  }
  return {
    source,
    params: { since, level: tab === "daemon" ? f.level : EVERYTHING_DAEMON_FLOOR },
  };
}

/** @ui-only A tab's count: a number, a floor ("500+"), or unknown. */
export type TabCount = ActivityCount;

const NONE: TabCount = { value: 0, floor: false };

/** @ui-only What the page renders from the feed. */
export interface ActivityFeed {
  /** The rows to show, newest first, filtered. */
  rows: ActivityRecord[];
  /** New records waiting behind "↑ N new", filtered. */
  pendingCount: number;
  /** Whether anything waits at all, filtered out or not. */
  hasPending: boolean;
  releaseAll: () => void;
  /** Each tab's count under the current time window and server-side filters. */
  counts: Record<ActivityTab, TabCount>;
  /** How many records are loaded (before client-side filters), and of how many. */
  loaded: number;
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
}

interface Args {
  tab: ActivityTab;
  filters: ActivityFilters;
  t: TFunction;
  agentNames: ReadonlyMap<string, string>;
  serverNames: ReadonlyMap<string, string>;
}

function countOf(state: ActivitySourceState): TabCount {
  return { value: state.total, floor: state.capped };
}

function sumCounts(parts: TabCount[]): TabCount {
  if (parts.length === 0) return { value: 0, floor: false };
  if (parts.some((p) => p.value === undefined)) return { value: undefined, floor: false };
  return {
    value: parts.reduce((n, p) => n + (p.value ?? 0), 0),
    floor: parts.some((p) => p.floor),
  };
}

export function useActivityFeed({ tab, filters, t, agentNames, serverNames }: Args): ActivityFeed {
  const { timeRange, from, to } = filters;
  // Memoised: a rolling preset's `since` is computed from Date.now(), and it
  // is part of every query key — recomputing it per render would refetch
  // every keystroke.
  const { since, until } = useMemo(
    () => resolveTimeWindow({ timeRange, from, to }),
    [timeRange, from, to],
  );

  const active = useMemo(() => new Set(sourcesFor(tab, filters)), [tab, filters]);

  // The three logs are always the same three hooks; a log this tab does not
  // read is simply switched off.
  const changeSpec = sourceParams("change", tab, filters, since);
  const callSpec = sourceParams("call", tab, filters, since);
  const daemonSpec = sourceParams("daemon", tab, filters, since);
  const change = useActivitySource(changeSpec, active.has("change"));
  const call = useActivitySource(callSpec, active.has("call"));
  const daemon = useActivitySource(daemonSpec, active.has("daemon"));

  const states = [change, call, daemon].filter((s) => active.has(s.source));
  const ctx: FilterContext = useMemo(
    () => ({ t, until, agentNames, serverNames }),
    [t, until, agentNames, serverNames],
  );
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

  // Each tab's count under the same time window. A count whose filters are
  // those of a log already in front reuses that log's head; any other is one
  // small read of its own.
  const specOf = (source: ActivitySource): SourceParams =>
    source === "change" ? changeSpec : source === "call" ? callSpec : daemonSpec;
  const sameAs = (spec: SourceParams): ActivitySourceState | undefined => {
    const wanted = JSON.stringify(spec);
    return [change, call, daemon].find(
      (s) => active.has(s.source) && JSON.stringify(specOf(s.source)) === wanted,
    );
  };
  const countSpecs = {
    changes: sourceParams("change", "changes", filters, since),
    callsAll: sourceParams("call", "everything", filters, since),
    callsTab: sourceParams("call", "mcp", filters, since),
    daemonAll: sourceParams("daemon", "everything", filters, since),
    daemonTab: sourceParams("daemon", "daemon", filters, since),
  };
  const everythingSources = sourcesFor("everything", filters);
  const reuse = {
    changes: sameAs(countSpecs.changes),
    callsAll: sameAs(countSpecs.callsAll),
    callsTab: sameAs(countSpecs.callsTab),
    daemonAll: sameAs(countSpecs.daemonAll),
    daemonTab: sameAs(countSpecs.daemonTab),
  };
  const read = {
    changes: useActivityCount(countSpecs.changes, !reuse.changes),
    callsAll: useActivityCount(
      countSpecs.callsAll,
      !reuse.callsAll && everythingSources.includes("call"),
    ),
    callsTab: useActivityCount(countSpecs.callsTab, !reuse.callsTab),
    daemonAll: useActivityCount(
      countSpecs.daemonAll,
      !reuse.daemonAll && everythingSources.includes("daemon"),
    ),
    daemonTab: useActivityCount(countSpecs.daemonTab, !reuse.daemonTab),
  };
  const pick = (name: keyof typeof countSpecs): TabCount => {
    const state = reuse[name];
    return state ? countOf(state) : read[name];
  };
  const counts: Record<ActivityTab, TabCount> = {
    everything: sumCounts([
      ...(everythingSources.includes("change") ? [pick("changes")] : []),
      ...(everythingSources.includes("call") ? [pick("callsAll")] : []),
      ...(everythingSources.includes("daemon") ? [pick("daemonAll")] : []),
    ]),
    changes: sourcesFor("changes", filters).length ? pick("changes") : NONE,
    mcp: sourcesFor("mcp", filters).length ? pick("callsTab") : NONE,
    daemon: sourcesFor("daemon", filters).length ? pick("daemonTab") : NONE,
  };

  // The frontier logs are the ones to page: loading an older page of any
  // other would only fetch rows still hidden behind the frontier.
  const pageable = states.filter((s) => s.hasOlder);
  const limiting = pageable.filter((s) => (s.oldestAt ?? 0) >= frontier);

  return {
    rows,
    pendingCount,
    hasPending: states.some((s) => s.pending.length > 0),
    releaseAll: () => states.forEach((s) => s.release()),
    counts,
    loaded: merged.length,
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
  };
}
