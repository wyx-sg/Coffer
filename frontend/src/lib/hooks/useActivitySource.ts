// src/lib/hooks/useActivitySource.ts — one of Activity's three logs: its loaded pages, its newest records and its count.
//
// Two reads per log. The **pages** are what the list shows: the first page,
// then one more per "Load older", read once and never refetched behind the
// reader's back, so a row being read never moves. The **head** is the newest
// page, re-read every few seconds (no log here is on the daemon's event
// stream, so this is the poll spec web-ui "Stream new Activity records while
// the list is at the top" allows) and on demand; a head row the pages do not
// hold is new, and waits in `pending` until the page releases it into view
// (at once while the reader is at the top, on "↑ N new" otherwise). The head
// also carries the log's `total`, which the tab counts show.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import {
  fetchAuditPage,
  fetchCallPage,
  fetchDaemonTail,
  MAX_PAGE,
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

/** Rows per "Load older". */
export const PAGE_SIZE = 200;
/** Rows the head re-reads; more new rows than this between two polls is a gap. */
const HEAD_SIZE = 50;
/** How often the head is re-read. */
export const HEAD_POLL_MS = 5_000;

interface Page {
  records: ActivityRecord[];
  next: string | null;
  /** Every row matching the filters; for the daemon tail, the rows it holds. */
  total: number | undefined;
  /** The daemon tail stopped at the route's cap: there may be more. */
  capped: boolean;
}

async function readPage(spec: SourceParams, limit: number, cursor: string | null): Promise<Page> {
  if (spec.source === "change") {
    const out = await fetchAuditPage(spec.params, limit, cursor);
    return {
      records: out.entries.map(fromAudit),
      next: out.next_cursor,
      total: out.total,
      capped: false,
    };
  }
  if (spec.source === "call") {
    const out = await fetchCallPage(spec.params, limit, cursor);
    return {
      records: out.invocations.map(fromCall),
      next: out.next_cursor,
      total: out.total,
      capped: false,
    };
  }
  const out = await fetchDaemonTail(spec.params, MAX_PAGE);
  return {
    records: fromDaemonTail(out.records),
    next: null,
    total: out.records.length,
    capped: out.records.length >= MAX_PAGE,
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
  /** The count is a floor (the daemon tail hit its cap). */
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
}

export function useActivitySource(spec: SourceParams, enabled: boolean): ActivitySourceState {
  const pagesKey = keyFor(spec, "pages");
  const identity = JSON.stringify(pagesKey);

  const pages = useInfiniteQuery({
    queryKey: pagesKey,
    queryFn: ({ pageParam }) => readPage(spec, PAGE_SIZE, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next ?? undefined,
    enabled,
    // What is on screen changes only when the reader asks: a new record comes
    // through the head, never by re-reading the pages under the reader.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const head = useQuery({
    queryKey: keyFor(spec, "head"),
    queryFn: () => readPage(spec, HEAD_SIZE, null),
    enabled,
    refetchInterval: HEAD_POLL_MS,
    refetchIntervalInBackground: false,
  });

  const loaded = useMemo(() => pages.data?.pages.flatMap((p) => p.records) ?? [], [pages.data]);

  const [extra, setExtra] = useState<{
    identity: string;
    accepted: ActivityRecord[];
    pending: ActivityRecord[];
  }>({ identity, accepted: [], pending: [] });
  // Other filters are another list: what was new under the old ones is not.
  const current = extra.identity === identity ? extra : { identity, accepted: [], pending: [] };

  const headRecords = head.data?.records;
  const pagesReady = pages.data !== undefined;
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

  const firstPage = pages.data?.pages[0];
  const { refetch: refetchHead } = head;
  const { refetch: refetchPages, fetchNextPage } = pages;
  const oldest = loaded.length > 0 ? loaded[loaded.length - 1].at : null;

  return {
    source: spec.source,
    records,
    pending: current.pending,
    release,
    total: head.data?.total ?? firstPage?.total,
    capped: head.data?.capped ?? firstPage?.capped ?? false,
    isLoading: enabled && pages.isLoading,
    error: pages.error,
    retry: () => void refetchPages(),
    hasOlder: pages.hasNextPage,
    loadOlder: () => void fetchNextPage(),
    isLoadingOlder: pages.isFetchingNextPage,
    refreshHead: () => void refetchHead(),
    oldestAt: oldest ? recordTimeMs(oldest) : undefined,
  };
}

/** How often a count beside a tab that is not in front is re-read. */
const COUNT_POLL_MS = 15_000;

/** @ui-only A log's count: every matching row, or a floor when the daemon tail hit its cap. */
export interface ActivityCount {
  value: number | undefined;
  floor: boolean;
}

/**
 * The count of one log under some filters, for a tab that is not in front —
 * one row's read for the paged logs (their answer carries `total`), the whole
 * bounded tail for the daemon log.
 */
export function useActivityCount(spec: SourceParams, enabled: boolean): ActivityCount {
  const query = useQuery({
    queryKey: keyFor(spec, "count"),
    queryFn: () => readPage(spec, 1, null),
    enabled,
    refetchInterval: COUNT_POLL_MS,
    refetchIntervalInBackground: false,
  });
  return { value: query.data?.total, floor: query.data?.capped ?? false };
}
