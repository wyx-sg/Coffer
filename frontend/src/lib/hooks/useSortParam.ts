// src/lib/hooks/useSortParam.ts — a table's sort kept in the URL (Foundations 0.6.02: "?sort=last_used").
//
// `?sort=key` is descending (the first click), `?sort=key:asc` ascending; no
// param is the default order. Replaces history entries — a sort is not a place.
// Pass the result to DataTable's `sort` / `onSortChange`.
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type { TableSort } from "@/lib/tableSort";

export function useSortParam(param = "sort"): [TableSort | null, (sort: TableSort | null) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get(param);
  const sort = useMemo<TableSort | null>(() => {
    if (!raw) return null;
    const [key, dir] = raw.split(":");
    return key ? { key, dir: dir === "asc" ? "asc" : "desc" } : null;
  }, [raw]);
  const setSort = useCallback(
    (next: TableSort | null) =>
      setParams(
        (prev) => {
          const out = new URLSearchParams(prev);
          if (next) out.set(param, next.dir === "asc" ? `${next.key}:asc` : next.key);
          else out.delete(param);
          return out;
        },
        { replace: true },
      ),
    [param, setParams],
  );
  return [sort, setSort];
}
