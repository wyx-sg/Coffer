// frontend/src/components/DataTableLoadMore.tsx — the list table's footer: "Showing x of y" and "Load N more".
//
// Foundations-Tables "Load more": a list is never paged by number. It shows
// the first N rows and grows by N at a time — N is the table's page size (the
// `pageSize` prop, else the Settings default). The count reads "Showing x of
// y" when the total is known and more remain — a list shown whole has no footer; the button is a small secondary one whose
// spinner replaces it while the next rows load. `useLoadMore` holds how many
// rows are shown, in either mode:
// - client (the caller passes every row): a limit over the filtered rows;
// - server (`serverPagination`, the caller passes one page at a time): each
//   page the caller hands over is kept, keyed by its number, so the rows of
//   pages 1..n are shown together, and Load more asks for page n+1. A caller
//   going back to page 1 (a new search) starts over.
// A list that pages by cursor instead (`useInfiniteList`) renders the shared
// `LoadMoreFooter` / `LoadMoreSentinel` of `components/ui/load-more.tsx`, which
// this footer is built on.
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { ServerPagination } from "@/components/DataTable.types";
import { LoadMoreFooter } from "@/components/ui/load-more";

interface LoadMoreArgs<T> {
  /** Client mode: every filtered row. Server mode: the page just handed over. */
  rows: T[];
  rowKey: (row: T) => string;
  size: number;
  server?: ServerPagination;
  /** Changes whenever the filtered set does (query, filters): shows N again. */
  resetKey: string;
}

export function useLoadMore<T>({ rows, rowKey, size, server, resetKey }: LoadMoreArgs<T>) {
  const [limit, setLimit] = useState(size);
  const [lastReset, setLastReset] = useState(resetKey);
  if (lastReset !== resetKey) {
    setLastReset(resetKey);
    setLimit(size);
  }

  // Server mode: every page seen since page 1, by number.
  const pages = useRef(new Map<number, T[]>());
  const serverPage = server?.page ?? 1;
  if (server) {
    if (serverPage <= 1) pages.current = new Map();
    pages.current.set(serverPage, rows);
  }
  const serverRows: T[] = [];
  if (server) {
    const seen = new Set<string>();
    for (let p = 1; p <= serverPage; p += 1) {
      for (const row of pages.current.get(p) ?? []) {
        const key = rowKey(row);
        if (!seen.has(key)) {
          seen.add(key);
          serverRows.push(row);
        }
      }
    }
  }
  const shown = server ? serverRows : rows.slice(0, Math.max(limit, size));
  const total = server ? server.total : rows.length;
  const more = () => {
    if (server) server.onPageChange(serverPage + 1);
    else setLimit((l) => Math.max(l, size) + size);
  };
  return { shown, total, more, hasMore: shown.length < total };
}

interface Props {
  shown: number;
  total: number;
  size: number;
  hasMore: boolean;
  loading: boolean;
  onMore: () => void;
}

/** The table's footer: the shared `LoadMoreFooter`, labelled with how many the next click adds. */
export function DataTableLoadMore({ shown, total, size, hasMore, loading, onMore }: Props) {
  const { t } = useTranslation();
  // Everything already on screen: a count would answer no question (principle 9).
  if (!hasMore) return null;
  return (
    <LoadMoreFooter
      loaded={shown}
      total={total}
      hasMore={hasMore}
      loading={loading}
      onMore={onMore}
      className="justify-between"
      moreLabel={t("pagination.loadMore", { count: Math.min(size, total - shown) })}
    />
  );
}
