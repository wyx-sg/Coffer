// frontend/src/components/DataTable.tsx
// The one reusable list table for every resource surface (Agents, MCP servers,
// Skills, …): search + filters, "Load N more" (Foundations-Tables — never
// numbered pages), optional row click→detail, and an optional `selection` prop
// (checkbox column + select-all + bulk bar over the filtered rows — see
// DataTableSelection.tsx). N is `pageSize`, else the Settings default. Two
// modes: client (default — caller passes ALL rows; filter and grow in memory)
// and server (caller passes ONE page + a `serverPagination` descriptor and
// drives search through `search.value`/`search.onChange`; each page it hands
// over is kept and shown under the ones before — DataTableLoadMore.tsx); and
// infinite (cursor-paged: every row passed is shown, see `InfiniteRows`).
// Row rendering lives in DataTableBody.tsx; sorting (DataTableSort.ts) and its
// props (DataTable.types.ts) are split out to keep this file within budget.
import { useMemo, useState } from "react";

import { sortRows } from "@/components/DataTableSort";
import { DataTableToolbar } from "@/components/DataTableToolbar";
import { DataTableHead } from "@/components/DataTableHead";
import { DataRows, EmptyRow, SkeletonRows } from "@/components/DataTableBody";
import { useTableSelection } from "@/components/DataTableSelection";
import { TableBulkBar, usePageSelectAll } from "@/components/DataTableBulk";
import { DataTableLoadMore, useLoadMore } from "@/components/DataTableLoadMore";
import { useDefaultPageSize } from "@/lib/preferences";
import { LoadMoreFooter } from "@/components/ui/load-more";
import { Table, TableBody } from "@/components/ui/table";
import {
  skeletonCount,
  type Column,
  type DataTableProps,
  type FilterDef,
  type TableSort,
} from "@/components/DataTable.types";
import { nextSort } from "@/lib/tableSort";
// Re-exported so call sites keep importing these from "@/components/DataTable".
export type { Column, FilterDef, TableSort };

// Cap the body at 20 rows (row ≈ 3rem) — beyond that the container scrolls
// vertically under the sticky header (#227), so a long list keeps its
// Load more and toolbar on screen. Tailwind's max-h scale stops at 24rem, so
// the value has to be arbitrary; it lives here, named, rather than inline.
const BODY_MAX_HEIGHT = "max-h-[60rem]";

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
  infinite,
  emptyMessage,
  emptyAction,
  fixed = false,
  sort: controlledSort,
  onSortChange,
  isLoading = false,
}: DataTableProps<T>) {
  const server = serverPagination;
  // Search may be controlled (server mode) or internal (client mode).
  const controlledQuery = search?.value;
  const [internalQuery, setInternalQuery] = useState("");
  const query = controlledQuery ?? internalQuery;
  const setQuery = (v: string) => {
    if (search?.onChange) search.onChange(v);
    else setInternalQuery(v);
  };

  const [internalSort, setInternalSort] = useState<TableSort | null>(null);
  const sort = controlledSort === undefined ? internalSort : controlledSort;
  const changeSort = (key: string) => {
    const next = nextSort(sort, key);
    if (onSortChange) onSortChange(next);
    else setInternalSort(next);
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

  const filtered = useMemo(
    () => (server ? rows : sortRows(clientFiltered, columns, sort)),
    [server, rows, clientFiltered, columns, sort],
  );

  const size = server ? server.pageSize : (pageSize ?? globalDefault);
  const resetKey = `${query}␟${JSON.stringify(filterVals)}␟${size}`;
  const loadMore = useLoadMore({ rows: filtered, rowKey, size, server, resetKey });
  const pageRows = infinite ? filtered : loadMore.shown;
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
  // The bulk bar takes the filter row's place while rows are ticked.
  const bulkShown = Boolean(selection) && (sel.selectedRows.length > 0 || ps.allMatching);
  const hasToolbar = (Boolean(search) || filters.length > 0) && !bulkShown;

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
        <Table
          containerClassName={BODY_MAX_HEIGHT}
          className={fixed ? "table-fixed" : undefined}
          aria-busy={isLoading || undefined}
        >
          <DataTableHead
            columns={columns}
            hasSelection={Boolean(selection)}
            expandable={expandable}
            allSelected={ps.pageAllSelected}
            someSelected={ps.pageSomeSelected}
            ariaSelectAll={selection?.ariaSelectAll}
            onToggleAll={ps.togglePage}
            sort={sort}
            onSort={changeSort}
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
            {infinite?.loading ? <SkeletonRows count={1} colCount={colCount} /> : null}
          </TableBody>
        </Table>
      </div>

      {infinite ? (
        <LoadMoreFooter
          loaded={infinite.loaded}
          total={infinite.total}
          hasMore={infinite.hasMore}
          loading={infinite.loading}
          onMore={infinite.onMore}
          autoLoad
        />
      ) : (
        <DataTableLoadMore
          shown={pageRows.length}
          total={total}
          size={size}
          hasMore={loadMore.hasMore}
          loading={Boolean(server) && isLoading}
          onMore={loadMore.more}
        />
      )}
    </div>
  );
}
