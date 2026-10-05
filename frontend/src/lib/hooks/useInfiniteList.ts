// src/lib/hooks/useInfiniteList.ts — the one hook behind every list that pages by cursor and grows as it is read.
//
// A list that can hold more than ~100 rows opens on one small page and reads
// the next when the reader scrolls to its end (`LoadMoreSentinel`) or presses
// "Load more" (`LoadMoreFooter`) — never all of it at once. The page is read
// by an opaque cursor the server hands back (`next`); the filters and the
// search text are part of the query key, so changing either starts again from
// the first page, and the request still in flight for the old ones is aborted
// (the abort signal is handed to `fetchPage`; the request function passes it
// on). A page already read is never re-read behind the reader's back unless
// the caller asks for a refetch interval.
import { keepPreviousData, useInfiniteQuery, type QueryKey } from "@tanstack/react-query";
import { useMemo } from "react";

/** @ui-only One page of a list: its rows, where the next page begins, and the count if the server knows it. */
export interface ListPage<T, X = undefined> {
  items: T[];
  /** Anything else the page carries that the surface shows (the agents a cross-agent list could not read). */
  extra?: X;
  /** The cursor of the next page; null when this was the last one. */
  next: string | null;
  total?: number;
  /** `total` is a floor: the server counted a bounded window and there may be more. */
  totalIsFloor?: boolean;
}

/** Rows in the first page of a list that opens small. */
export const FIRST_PAGE = 30;
/** Rows in every page after it. */
export const MORE_PAGE = 50;

interface Args<T, X> {
  queryKey: QueryKey;
  /** Reads the page at `cursor` (null for the first); `signal` aborts it. */
  fetchPage: (cursor: string | null, signal: AbortSignal) => Promise<ListPage<T, X>>;
  enabled?: boolean;
  /** Re-read every page this often (ms); leave out for a list that is read once. */
  refetchInterval?: number;
  /** Keep showing the previous filters' rows while the new ones load (default true). */
  keepPrevious?: boolean;
  /** How long a read page stays fresh (ms); `Infinity` for a list that changes only when the reader asks. */
  staleTime?: number;
  /** Read the pages again when the window regains focus (default off). */
  refetchOnFocus?: boolean;
}

/** @ui-only What a list surface renders from. */
export interface InfiniteList<T, X = undefined> {
  /** Every row loaded so far, in the order the server gave them. */
  items: T[];
  /** What each page read so far carried besides its rows, in page order. */
  extras: X[];
  /** The server's count of every matching row, when it gave one. */
  total: number | undefined;
  totalIsFloor: boolean;
  hasMore: boolean;
  loadMore: () => void;
  /** Reads every page left, one after another — only for an explicit ask that
   *  needs them all (Select all), never to fill the screen. */
  loadAll: () => Promise<void>;
  /** The first page is loading (nothing to show yet). */
  isLoading: boolean;
  /** A later page is loading. */
  isLoadingMore: boolean;
  /** A new filter's first page is loading over the previous filter's rows. */
  isRefreshing: boolean;
  error: unknown;
  refetch: () => void;
}

export function useInfiniteList<T, X = undefined>({
  queryKey,
  fetchPage,
  enabled = true,
  refetchInterval,
  keepPrevious = true,
  staleTime,
  refetchOnFocus = false,
}: Args<T, X>): InfiniteList<T, X> {
  const query = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam, signal }) => fetchPage(pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next ?? undefined,
    enabled,
    placeholderData: keepPrevious ? keepPreviousData : undefined,
    refetchInterval,
    staleTime,
    refetchIntervalInBackground: false,
    // A page that is on screen changes when the reader asks, or on the
    // caller's interval — and on focus only for a list that asks for it.
    refetchOnWindowFocus: refetchOnFocus,
  });
  const items = useMemo(() => query.data?.pages.flatMap((p) => p.items) ?? [], [query.data]);
  const extras = useMemo(
    () => (query.data?.pages ?? []).flatMap((p) => (p.extra === undefined ? [] : [p.extra])),
    [query.data],
  );
  // The first page's total is the freshest the server gave for this query.
  const total = query.data?.pages[0]?.total;
  const { fetchNextPage, refetch } = query;
  return {
    items,
    extras,
    total,
    totalIsFloor: query.data?.pages[0]?.totalIsFloor ?? false,
    hasMore: query.hasNextPage,
    loadMore: () => {
      if (query.hasNextPage && !query.isFetchingNextPage) void fetchNextPage();
    },
    loadAll: async () => {
      let more = query.hasNextPage;
      while (more) {
        const result = await fetchNextPage();
        more = result.hasNextPage && !result.isError;
      }
    },
    isLoading: enabled && query.isLoading,
    isLoadingMore: query.isFetchingNextPage,
    isRefreshing: query.isPlaceholderData && query.isFetching,
    error: query.error,
    refetch: () => void refetch(),
  };
}
