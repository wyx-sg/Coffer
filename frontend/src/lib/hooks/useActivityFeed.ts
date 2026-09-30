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

import type { CallParams, SourceParams } from "@/lib/api/activity";
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
  // A change's kind is a category the audit route does not know (secrets,
  // sync, settings), so the kind filter is applied on the client.
  if (source === "change") return { source, params: { since } };
  if (source === "call") {
    return {
      source,
      params: {
        since,
        uid: f.server !== "any" ? f.server : undefined,
        status: tab === "mcp" && isCallStatus(f.status) ? f.status : undefined,
        agentUid: singleAgent(tab, f),
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
  /** Every loaded record before the client-side filters, for the pills' counts. */
  loadedRecords: ActivityRecord[];
  /**
   * On the MCP calls tab with no status chosen: how many calls in the window
   * failed (an error or a timeout) and how many were denied.
   */
  callTally: { failed: number; denied: number } | undefined;
  /** The daemon log's file, when this tab reads it. */
  logPath: string | undefined;
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
  // The counts beside the tabs follow the time window, the server and the
  // status, not who or what kind: choosing agents or kinds narrows the list,
  // while the tabs keep saying how much there is (design 6.1.03, 6.1.04).
  const framing: ActivityFilters = { ...filters, by: [], kinds: [] };
  const countSpecs = {
    changes: sourceParams("change", "changes", framing, since),
    callsAll: sourceParams("call", "everything", framing, since),
    callsTab: sourceParams("call", "mcp", framing, since),
    daemonAll: sourceParams("daemon", "everything", framing, since),
    daemonTab: sourceParams("daemon", "daemon", framing, since),
  };
  const everythingSources = sourcesFor("everything", framing);
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
  // The MCP calls tab's line ("182 calls · 7 failed · 1 denied"): one row's
  // read per outcome, as the tab counts are.
  const tallyOn = tab === "mcp" && filters.status === "any" && active.has("call");
  const withStatus = (status: "error" | "timeout" | "denied"): SourceParams => ({
    source: "call",
    params: { ...(callSpec.params as CallParams), status },
  });
  const errors = useActivityCount(withStatus("error"), tallyOn);
  const timeouts = useActivityCount(withStatus("timeout"), tallyOn);
  const denied = useActivityCount(withStatus("denied"), tallyOn);
  const callTally =
    tallyOn &&
    errors.value !== undefined &&
    timeouts.value !== undefined &&
    denied.value !== undefined
      ? { failed: errors.value + timeouts.value, denied: denied.value }
      : undefined;

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
    changes: sourcesFor("changes", framing).length ? pick("changes") : NONE,
    mcp: sourcesFor("mcp", framing).length ? pick("callsTab") : NONE,
    daemon: sourcesFor("daemon", framing).length ? pick("daemonTab") : NONE,
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
    loadedRecords: merged,
    callTally,
    logPath: active.has("daemon") ? daemon.path : undefined,
  };
}
