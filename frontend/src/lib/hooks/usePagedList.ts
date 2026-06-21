// frontend/src/lib/hooks/usePagedList.ts
//
// Page-based pagination for list surfaces (KB documents, memory facts). Pairs a
// 1-based page + page size with an optional debounced server-side filter, and
// keeps the page in range as the result set changes. `usePagedList` owns the
// state; `usePageClamp` pulls the page back when the total shrinks (e.g. the
// last page is emptied) so the user is never stranded on an empty page.
import { useEffect, useState } from "react";

// Debounce (ms) before the filter value is applied, so typing doesn't fire a
// request per keystroke.
const FILTER_DEBOUNCE_MS = 300;

export function usePagedList(defaultPageSize: number) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(defaultPageSize);
  const [filter, setFilter] = useState("");
  const [filterApplied, setFilterApplied] = useState("");

  // Debounce the filter before it becomes the query input.
  useEffect(() => {
    const id = setTimeout(() => setFilterApplied(filter), FILTER_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [filter]);

  // A new filter or page size can shrink the result set: jump back to page 1.
  useEffect(() => {
    setPage(1);
  }, [filterApplied, pageSize]);

  const offset = (page - 1) * pageSize;
  return { page, setPage, pageSize, setPageSize, filter, setFilter, filterApplied, offset };
}

// Pull a 1-based page back into range when `pageCount` drops below it (the total
// shrank — e.g. the last page's rows were all deleted), so a list surface never
// strands the user on an empty page past the end.
export function usePageClamp(page: number, pageCount: number, setPage: (page: number) => void) {
  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount, setPage]);
}
