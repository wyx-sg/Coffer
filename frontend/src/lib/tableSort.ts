// src/lib/tableSort.ts — the sort a table can be in (Foundations 0.6.02), shared by DataTable and the URL hook.

/** The one active sort: a column key and its direction. Null = the default order. */
export interface TableSort {
  key: string;
  dir: "asc" | "desc";
}

/** Three-state cycle on one column: desc → asc → default; another column starts at desc. */
export function nextSort(current: TableSort | null, key: string): TableSort | null {
  if (current?.key !== key) return { key, dir: "desc" };
  return current.dir === "desc" ? { key, dir: "asc" } : null;
}
