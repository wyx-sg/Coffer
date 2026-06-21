// frontend/src/components/DataTable.types.ts
// Shared types for the DataTable family (DataTable.tsx, DataTableHead.tsx,
// DataTableToolbar.tsx, DataTableSelection.tsx). Kept apart from DataTable.tsx
// so that file stays within its size budget; DataTable re-exports these so call
// sites keep importing them from "@/components/DataTable".
import { type ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** Classes applied to both <th> and <td> (e.g. text-right for actions). */
  className?: string;
}

export interface FilterDef<T> {
  key: string;
  label: string;
  allLabel: string;
  options: { value: string; label: string }[];
  /** Value extracted from a row to compare against the selected option. */
  accessor: (row: T) => string;
}

export interface TableSelection<T> {
  ariaSelectAll: string;
  ariaSelectRow: (row: T) => string;
  /** Bar label, e.g. "3 selected". */
  bulkLabel: (count: number) => string;
  clearLabel: string;
  /** Action buttons rendered in the bar while ≥1 row is selected. */
  renderBulkActions: (args: { selectedRows: T[]; clear: () => void }) => ReactNode;
}

/** Server-driven pagination: the caller passes one page of `rows` and owns the
 * page/pageSize state. When set, client-side search/filter/slice are skipped. */
export interface ServerPagination {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}
