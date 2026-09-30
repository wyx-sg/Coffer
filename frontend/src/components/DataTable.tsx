// frontend/src/components/DataTable.tsx
// The one reusable list table for every resource surface (Agents, MCP servers,
// Skills, …): search + filters, "Load N more" (Foundations-Tables — never
// numbered pages), optional row click→detail, and an optional `selection` prop
// (checkbox column + select-all + bulk bar over the filtered rows — see
// DataTableSelection.tsx). N is `pageSize`, else the Settings default. Two
// modes: client (default — caller passes ALL rows; filter and grow in memory)
// and server (caller passes ONE page + a `serverPagination` descriptor and
// drives search through `search.value`/`search.onChange`; each page it hands
// over is kept and shown under the ones before — DataTableLoadMore.tsx).
// Row rendering (data rows, skeleton rows, the empty state) lives in
// DataTableBody.tsx.
import { useMemo, useState, type ReactNode } from "react";

import { DataTableToolbar } from "@/components/DataTableToolbar";
import { DataTableHead } from "@/components/DataTableHead";
import { DataRows, EmptyRow, SkeletonRows } from "@/components/DataTableBody";
import { useTableSelection } from "@/components/DataTableSelection";
import { TableBulkBar, usePageSelectAll } from "@/components/DataTableBulk";
import { DataTableLoadMore, useLoadMore } from "@/components/DataTableLoadMore";
import { useDefaultPageSize } from "@/lib/preferences";
import { Table, TableBody } from "@/components/ui/table";
import {
  skeletonCount,
  type Column,
  type FilterDef,
  type ListLoading,
  type ServerPagination,
  type TableSelection,
} from "@/components/DataTable.types";
// Re-exported so call sites keep importing these from "@/components/DataTable".
export type { Column, FilterDef };

// Cap the body at 20 rows (row ≈ 3rem) — beyond that the container scrolls
// vertically under the sticky header (#227), so a long list keeps its
// Load more and toolbar on screen. Tailwind's max-h scale stops at 24rem, so
// the value has to be arbitrary; it lives here, named, rather than inline.
const BODY_MAX_HEIGHT = "max-h-[60rem]";

interface Props<T> extends ListLoading {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  // Search box: `accessor` drives the client-side filter (omit in server mode);
  // `value`/`onChange` make it a controlled input that searches the server.
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
  /** How many rows show at first and each "Load N more" adds (default: Settings). */
  pageSize?: number;
  /** When set, page on demand against the server instead of slicing in memory. */
  serverPagination?: ServerPagination;
  emptyMessage: string;
  /** Rendered under the empty message, e.g. the primary "create" button. */
  emptyAction?: ReactNode;
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  search,
  filters = [],
  onRowClick,
  isRowClickable,
  rowFooter,
  getRowDetail,
  selection,
  isSelectable,
  pageSize,
  serverPagination,
  emptyMessage,
  emptyAction,
  isLoading = false,
}: Props<T>) {
  const server = serverPagination;
  // Search may be controlled (server mode) or internal (client mode).
  const controlledQuery = search?.value;
  const [internalQuery, setInternalQuery] = useState("");
  const query = controlledQuery ?? internalQuery;
  const setQuery = (v: string) => {
    if (search?.onChange) search.onChange(v);
    else setInternalQuery(v);
  };

  const [filterVals, setFilterVals] = useState<Record<string, string>>({});
  // N: the `pageSize` prop, else the Settings default (reactive to Settings).
  const globalDefault = useDefaultPageSize();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const expandable = Boolean(getRowDetail);
  const colCount = columns.length + (expandable ? 1 : 0) + (selection ? 1 : 0);
  const toggleExpand = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  // Client-side filter (search + dropdown filters). Unused in server mode, where
  // the caller has already fetched the matching page.
  const clientFiltered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (q && search?.accessor && !search.accessor(row).toLowerCase().includes(q)) return false;
      for (const f of filters) {
        const v = filterVals[f.key];
        if (v && v !== "all" && f.accessor(row) !== v) return false;
      }
      return true;
    });
  }, [rows, query, filterVals, filters, search]);

  const filtered = server ? rows : clientFiltered;

  const size = server ? server.pageSize : (pageSize ?? globalDefault);
  const resetKey = `${query}␟${JSON.stringify(filterVals)}␟${size}`;
  const loadMore = useLoadMore({ rows: filtered, rowKey, size, server, resetKey });
  const pageRows = loadMore.shown;
  const total = loadMore.total;
  // Selection derives from the *filtered* set so bulk actions only touch
  // matching rows (in server mode: the rows loaded so far).
  const selectable = server ? pageRows : filtered;
  const sel = useTableSelection(selectable, rowKey);

  const canSelect = (r: T) => (isSelectable ? isSelectable(r) : true);
  // Header checkbox selects the CURRENT PAGE; TableBulkBar escalates to "all".
  const ps = usePageSelectAll({
    sel,
    pageRows,
    filtered: selectable,
    rowKey,
    canSelect,
    total,
    server: Boolean(server),
    resetKey,
  });
  const hasToolbar = Boolean(search) || filters.length > 0;

  return (
    <div className="space-y-4">
      {hasToolbar ? (
        <DataTableToolbar
          query={query}
          onQueryChange={(v) => {
            setQuery(v);
            if (server) server.onPageChange(1);
          }}
          searchPlaceholder={search?.placeholder}
          filters={filters}
          filterVals={filterVals}
          onFilterChange={(key, v) => {
            setFilterVals((prev) => ({ ...prev, [key]: v }));
          }}
        />
      ) : null}

      {selection ? (
        <TableBulkBar selection={selection} ps={ps} selectedRows={sel.selectedRows} />
      ) : null}

      <div className="overflow-hidden rounded-xl border border-border bg-surface-raised">
        <Table containerClassName={BODY_MAX_HEIGHT} aria-busy={isLoading || undefined}>
          <DataTableHead
            columns={columns}
            hasSelection={Boolean(selection)}
            expandable={expandable}
            allSelected={ps.pageAllSelected}
            someSelected={ps.pageSomeSelected}
            ariaSelectAll={selection?.ariaSelectAll}
            onToggleAll={ps.togglePage}
          />
          <TableBody>
            {isLoading && pageRows.length === 0 ? (
              <SkeletonRows count={skeletonCount(size)} colCount={colCount} />
            ) : pageRows.length === 0 ? (
              <EmptyRow colCount={colCount} message={emptyMessage} action={emptyAction} />
            ) : (
              <DataRows
                rows={pageRows}
                columns={columns}
                rowKey={rowKey}
                colCount={colCount}
                onRowClick={onRowClick}
                isRowClickable={isRowClickable}
                rowFooter={rowFooter}
                getRowDetail={getRowDetail}
                expanded={expanded}
                onToggleExpand={toggleExpand}
                selection={selection}
                canSelect={canSelect}
                selectedKeys={sel.keys}
                onToggleSelect={sel.toggle}
              />
            )}
          </TableBody>
        </Table>
      </div>

      <DataTableLoadMore
        shown={pageRows.length}
        total={total}
        size={size}
        hasMore={loadMore.hasMore}
        loading={Boolean(server) && isLoading}
        onMore={loadMore.more}
      />
    </div>
  );
}
