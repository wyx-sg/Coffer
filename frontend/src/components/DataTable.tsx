// frontend/src/components/DataTable.tsx
// The one reusable list table for every resource surface (Agents, MCP servers,
// Skills, …): search + filters, optional row click→detail, and an optional
// `selection` prop (checkbox column + select-all + bulk bar over the filtered
// rows — see DataTableSelection.tsx). Never numbered pages (Foundations-Tables).
// Two modes: client (default — caller passes ALL rows; they filter in memory
// and render whole, or 100 at a time as the end scrolls into view when there are
// more than that — `useGrowingList`) and infinite (cursor-paged: every row
// passed is shown and the next page loads on scroll, see `InfiniteRows`).
// Row rendering lives in DataTableBody.tsx; sorting (DataTableSort.ts) and its
// props (DataTable.types.ts) are split out to keep this file within budget.
import { useMemo, useState } from "react";

import { sortRows } from "@/components/DataTableSort";
import { DataTableToolbar } from "@/components/DataTableToolbar";
import { DataTableHead } from "@/components/DataTableHead";
import { DataRows, EmptyRow, SkeletonRows } from "@/components/DataTableBody";
import { useTableSelection } from "@/components/DataTableSelection";
import { TableBulkBar, usePageSelectAll } from "@/components/DataTableBulk";
import { useGrowingList } from "@/lib/hooks/useGrowingList";
import { LoadMoreFooter, LoadMoreSentinel } from "@/components/ui/load-more";
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

// Cap the body at 20 rows (row ≈ 3rem): beyond that it scrolls under the
// sticky header (#227), keeping Load more and the toolbar on screen. Tailwind's
// max-h scale stops at 24rem, so the arbitrary value lives here, named.
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
  infinite,
  emptyMessage,
  emptyAction,
  fixed = false,
  footer = true,
  sort: controlledSort,
  onSortChange,
  isLoading = false,
}: DataTableProps<T>) {
  // Search may be controlled by the caller or internal.
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

  // Client-side filter (search + dropdown filters).
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
    () => sortRows(clientFiltered, columns, sort),
    [clientFiltered, columns, sort],
  );

  const resetKey = `${query}␟${JSON.stringify(filterVals)}`;
  const grow = useGrowingList(filtered, resetKey);
  const pageRows = infinite ? filtered : grow.shown;
  const total = filtered.length;
  // Selection derives from the *filtered* set so bulk actions only touch
  // matching rows.
  const sel = useTableSelection(filtered, rowKey);

  const canSelect = (r: T) => (isSelectable ? isSelectable(r) : true);
  // Header checkbox selects the CURRENT PAGE; TableBulkBar escalates to "all".
  const ps = usePageSelectAll({
    sel,
    pageRows,
    filtered,
    rowKey,
    canSelect,
    total,
    resetKey,
  });
  // The bulk bar takes the filter row's place while rows are ticked.
  const bulkShown = Boolean(selection) && sel.selectedRows.length > 0;
  const hasToolbar = (Boolean(search) || filters.length > 0) && !bulkShown;

  return (
    <div className="space-y-4">
      {hasToolbar ? (
        <DataTableToolbar
          query={query}
          onQueryChange={(v) => {
            setQuery(v);
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
              <SkeletonRows count={skeletonCount()} colCount={colCount} />
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

      {!footer ? null : infinite ? (
        <LoadMoreFooter
          loaded={infinite.loaded}
          total={infinite.total}
          hasMore={infinite.hasMore}
          loading={infinite.loading}
          onMore={infinite.onMore}
          autoLoad
          countLabel={infinite.countLabel}
        />
      ) : grow.hasMore ? (
        <LoadMoreSentinel active onVisible={grow.more} version={pageRows.length} />
      ) : null}
    </div>
  );
}
