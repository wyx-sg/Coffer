// src/components/DataTableSort.ts — orders DataTable rows by the active sort column.
//
// Numbers compare as numbers, ISO strings and Dates as times; a row with no value
// sorts last in either direction so "—" never leads a "largest first" column.
// Without an active sort (or a `sortValue`) the caller's order stands.
import type { Column } from "@/components/DataTable.types";
import type { TableSort } from "@/lib/tableSort";

function toNumber(v: number | string | Date): number {
  if (typeof v === "number") return v;
  return v instanceof Date ? v.getTime() : new Date(v).getTime();
}

export function sortRows<T>(rows: T[], columns: Column<T>[], sort: TableSort | null): T[] {
  const column = sort ? columns.find((c) => c.key === sort.key) : undefined;
  const value = column?.sortValue;
  if (!sort || !value) return rows;
  const sign = sort.dir === "desc" ? -1 : 1;
  return rows
    .map((row, index) => {
      const v = value(row);
      return { row, index, n: v === null ? null : toNumber(v) };
    })
    .sort((a, b) => {
      if (a.n === null || Number.isNaN(a.n))
        return b.n === null || Number.isNaN(b.n) ? a.index - b.index : 1;
      if (b.n === null || Number.isNaN(b.n)) return -1;
      return a.n === b.n ? a.index - b.index : (a.n - b.n) * sign;
    })
    .map((x) => x.row);
}
