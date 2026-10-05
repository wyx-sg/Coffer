// frontend/src/components/DataTable.types.ts
// Shared types for the DataTable family (DataTable.tsx, DataTableHead.tsx,
// DataTableToolbar.tsx, DataTableSelection.tsx). Kept apart from DataTable.tsx
// so that file stays within its size budget; DataTable re-exports these so call
// sites keep importing them from "@/components/DataTable".
import { type ReactNode } from "react";

import type { TableSort } from "@/lib/tableSort";

export type { TableSort };

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** Classes applied to both <th> and <td> (e.g. text-right for actions). */
  className?: string;
  /** Makes the header a sort control (Foundations 0.6.02 — number and time columns only; names,
   *  kinds and status never sort). Click sorts descending (largest / newest first), again
   *  ascending, a third time restores the default order. Rows are ordered by `sortValue` in
   *  the table's own client mode; with a controlled `sort` (server data) the caller orders. */
  sortable?: boolean;
  /** The number, or ISO / Date time, this column sorts on; null sorts last. */
  sortValue?: (row: T) => number | string | Date | null;
}

export interface FilterDef<T> {
  key: string;
  label: string;
  options: { value: string; label: string }[];
  /** Value extracted from a row to compare against the selected option. */
  accessor: (row: T) => string;
}

export interface TableSelection<T> {
  ariaSelectAll: string;
  ariaSelectRow: (row: T) => string;
  /** Action buttons rendered in the bulk bar (it reads "N of M selected" and ends in Clear
   * itself) while ≥1 row is selected. */
  renderBulkActions: (args: { selectedRows: T[]; clear: () => void }) => ReactNode;
}

/** Loading-state contract for DataTable. */
interface ListLoading {
  /** While true, a few skeleton rows stand in for the data
   *  (never an empty surface). Omit to keep the plain "render what you have"
   *  behaviour. */
  isLoading?: boolean;
}

/** How many skeleton rows stand in for the data while it loads: a pulsing wall of
 *  100 rows reads as a fault, not as loading. */
const SKELETON_ROWS = 5;

export function skeletonCount(): number {
  return SKELETON_ROWS;
}

/** A list that grows by cursor (`useInfiniteList`): the caller passes every row
 * loaded so far, and the table shows them all, a skeleton row while the next
 * page loads, and the shared load-more footer (it also loads on scroll). */
interface InfiniteRows {
  /** Rows loaded so far, as the server counts them (rows shown may be fewer if the caller folds). */
  loaded: number;
  total?: number;
  hasMore: boolean;
  /** A later page is loading. */
  loading: boolean;
  onMore: () => void;
  /** The footer's count wording, when "Showing N of M" would name the wrong thing (rows folded from rounds, say). */
  countLabel?: (loaded: number, total?: number) => string;
}

export interface DataTableProps<T> extends ListLoading {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  // Search box: `accessor` drives the client-side filter;
  // `value`/`onChange` make it a controlled input.
  search?: {
    accessor?: (row: T) => string;
    placeholder: string;
    value?: string;
    onChange?: (v: string) => void;
  };
  filters?: FilterDef<T>[];
  onRowClick?: (row: T) => void;
  /** Rows returning false do not open on click (default: all do). */
  isRowClickable?: (row: T) => boolean;
  /** A full-width row under a row — a notice about it; null renders nothing. */
  rowFooter?: (row: T) => ReactNode;
  /** When set, rows expand to a full-width detail sub-row (excludes onRowClick). */
  getRowDetail?: (row: T) => ReactNode;
  /** When set, a leading checkbox column + bulk action bar are rendered. */
  selection?: TableSelection<T>;
  /** Rows returning false get no checkbox + are excluded from bulk (default: all). */
  isSelectable?: (row: T) => boolean;
  infinite?: InfiniteRows;
  /** Fixed table layout: columns take the widths their `className` sets (e.g.
   *  `w-[36%]`) and the rest share what is left, so no cell stretches the table.
   *  Pair it with `TruncatedText` / `TruncatedPath` in cells that can be long. */
  fixed?: boolean;
  /** The active sort, controlled — for server data and for a sort kept in the URL. Omit and the
   *  table keeps it itself (the default order until a sortable header is clicked). */
  sort?: TableSort | null;
  onSortChange?: (sort: TableSort | null) => void;
  emptyMessage: string;
  /** false drops the "Showing x of y" footer (an always-short list). */
  footer?: boolean;
  /** Rendered under the empty message, e.g. the primary "create" button. */
  emptyAction?: ReactNode;
}
