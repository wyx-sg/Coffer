// src/lib/hooks/useActivitySource.ts — one of Activity's three logs: its loaded pages, its newest records and its count.
//
// Three reads per log, each small. The **pages** are what the list shows: a
// first page of 30, then 50 more each time the reader scrolls to the end or
// asks (`useInfiniteList`), read once and never refetched behind the reader's
// back, so a row being read never moves. The **head** is the newest few
// records, re-read every few seconds (no log here is on the daemon's event
// stream, so this is the poll spec web-ui "Stream new Activity records while
// the list is at the top" allows) and on demand; a head row the pages do not
// hold is new, and waits in `pending` until the page releases it into view
// (at once while the reader is at the top, on "↑ N new" otherwise). The
// **count** is one row's read that carries the log's `total`, for the tab
// labels, re-read rarely.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  fetchAuditPage,
  fetchCallPage,
  fetchDaemonPage,
  type SourceParams,
} from "@/lib/api/activity";
import { auditListKey, daemonLogsKey, mcpAllInvocationsKey } from "@/lib/api/queryKeys";
import {
  fromAudit,
  fromCall,
  fromDaemonTail,
  mergeNewestFirst,
  recordTimeMs,
  type ActivityRecord,
  type ActivitySource,
} from "@/lib/activity/records";
import { FIRST_PAGE, MORE_PAGE, useInfiniteList, type ListPage } from "./useInfiniteList";

/** Rows the head re-reads; more new rows than this between two polls is a gap. */
const HEAD_SIZE = 20;
/** How often the head is re-read. */
const HEAD_POLL_MS = 5_000;
/** How often a count is re-read. */
const COUNT_POLL_MS = 60_000;

/** The file the daemon log is read from, once its first page has been. */
interface Read extends ListPage<ActivityRecord> {
  path?: string;
}

async function readPage(
  spec: SourceParams,
  limit: number,
  cursor: string | null,
  signal: AbortSignal,
  withTotal = false,
): Promise<Read> {
  if (spec.source === "change") {
    const out = await fetchAuditPage(spec.params, limit, cursor, signal);
    return { items: out.entries.map(fromAudit), next: out.next_cursor, total: out.total };
  }
  if (spec.source === "call") {
    const out = await fetchCallPage(spec.params, limit, cursor, signal);
    return { items: out.invocations.map(fromCall), next: out.next_cursor, total: out.total };
  }
  const out = await fetchDaemonPage(spec.params, limit, cursor, signal, withTotal);
  return {
    items: fromDaemonTail(out.records),
    next: out.next_cursor ?? null,
    total: out.total ?? undefined,
    totalIsFloor: out.total_is_floor,
    path: out.path,
  };
}

function keyFor(spec: SourceParams, view: "pages" | "head" | "count") {
  const filters = { ...spec.params, view };
  if (spec.source === "change") return auditListKey(filters);
  if (spec.source === "call") return mcpAllInvocationsKey(filters);
  return daemonLogsKey(filters);
}

/** @ui-only What the page gets for one log. */
export interface ActivitySourceState {
  source: ActivitySource;
  /** Released new records, then the loaded pages: newest first. */
  records: ActivityRecord[];
  /** New records waiting for the page to release them. */
  pending: ActivityRecord[];
  /** Move every pending record into `records`. */
  release: () => void;
  total: number | undefined;
  /** The count is a floor (the daemon log counts a bounded tail). */
  capped: boolean;
  isLoading: boolean;
  error: unknown;
  retry: () => void;
  hasOlder: boolean;
  loadOlder: () => void;
  isLoadingOlder: boolean;
  /** Re-read the head now (a change event just arrived). */
  refreshHead: () => void;
  /** The time of the oldest loaded record, for merging several logs. */
  oldestAt: number | undefined;
  /** The daemon log's file, once it has been read. */
  path: string | undefined;
}

export function useActivitySource(spec: SourceParams, enabled: boolean): ActivitySourceState {
  const pagesKey = keyFor(spec, "pages");
  const identity = JSON.stringify(pagesKey);

  const pages = useInfiniteList<ActivityRecord>({
    queryKey: pagesKey,
    fetchPage: async (cursor, signal) => {
      const page = await readPage(spec, cursor ? MORE_PAGE : FIRST_PAGE, cursor, signal);
      return page;
    },
    enabled,
    // What is on screen changes only when the reader asks: a new record comes
    // through the head, never by re-reading the pages under the reader.
    staleTime: Infinity,
    keepPrevious: false,
  });

  const head = useQuery({
    queryKey: keyFor(spec, "head"),
    queryFn: ({ signal }) => readPage(spec, HEAD_SIZE, null, signal),
    // Not alongside the first page, which already holds the newest rows.
    enabled: enabled && !pages.isLoading,
    refetchInterval: HEAD_POLL_MS,
    refetchIntervalInBackground: false,
  });
  // The daemon log counts a bounded tail: that read is not repeated per poll.
  const count = useActivityCount(spec, enabled && spec.source === "daemon");

  const loaded = pages.items;
  const [extra, setExtra] = useState<{
    identity: string;
    accepted: ActivityRecord[];
    pending: ActivityRecord[];
  }>({ identity, accepted: [], pending: [] });
  // Other filters are another list: what was new under the old ones is not.
  const current = extra.identity === identity ? extra : { identity, accepted: [], pending: [] };

  const headRecords = head.data?.items;
  const pagesReady = loaded.length > 0 || !pages.isLoading;
  useEffect(() => {
    if (!pagesReady || !headRecords) return;
    setExtra((prev) => {
      const base = prev.identity === identity ? prev : { identity, accepted: [], pending: [] };
      const known = new Set<string>();
      for (const r of loaded) known.add(r.key);
      for (const r of base.accepted) known.add(r.key);
      for (const r of base.pending) known.add(r.key);
      const newest = loaded.length > 0 ? recordTimeMs(loaded[0].at) : 0;
      const add = headRecords.filter((r) => !known.has(r.key) && recordTimeMs(r.at) >= newest);
      if (add.length === 0) return base === prev ? prev : base;
      return { ...base, pending: mergeNewestFirst([add, base.pending]) };
    });
  }, [headRecords, pagesReady, loaded, identity]);

  const release = useCallback(() => {
    setExtra((prev) => {
      if (prev.identity !== identity || prev.pending.length === 0) return prev;
      return {
        identity,
        accepted: mergeNewestFirst([prev.pending, prev.accepted]),
        pending: [],
      };
    });
  }, [identity]);

  const records = useMemo(
    () => (current.accepted.length ? mergeNewestFirst([current.accepted, loaded]) : loaded),
    [current.accepted, loaded],
  );

  const { refetch: refetchHead } = head;
  const oldest = loaded.length > 0 ? loaded[loaded.length - 1].at : null;
  const own =
    spec.source === "daemon" ? count : { value: head.data?.total ?? pages.total, floor: false };

  return {
    source: spec.source,
    records,
    pending: current.pending,
    release,
    total: own.value ?? pages.total,
    capped: own.floor || pages.totalIsFloor,
    isLoading: pages.isLoading,
    error: pages.error,
    retry: pages.refetch,
    hasOlder: pages.hasMore,
    loadOlder: pages.loadMore,
    isLoadingOlder: pages.isLoadingMore,
    refreshHead: () => void refetchHead(),
    oldestAt: oldest ? recordTimeMs(oldest) : undefined,
    path: head.data?.path,
  };
}

/** @ui-only A log's count: every matching row, or a floor when the daemon log counted a bounded tail. */
interface ActivityCount {
  value: number | undefined;
  floor: boolean;
}

/**
 * The count of one log under some filters, for a tab label — one row's read
 * (the paged logs answer with `total`; the daemon log counts its recent tail
 * when asked). Re-read once a minute, not on every poll of the list.
 */
function useActivityCount(spec: SourceParams, enabled: boolean): ActivityCount {
  const query = useQuery({
    queryKey: keyFor(spec, "count"),
    queryFn: ({ signal }) => readPage(spec, 1, null, signal, true),
    enabled,
    refetchInterval: COUNT_POLL_MS,
    refetchIntervalInBackground: false,
  });
  return { value: query.data?.total, floor: query.data?.totalIsFloor ?? false };
}
