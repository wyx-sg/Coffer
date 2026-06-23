// frontend/src/components/DataTable.tsx
// The one reusable list table for every resource surface (Agents, MCP servers,
// Skills, …): search + filters + pagination, optional row click→detail, and an
// optional `selection` prop (checkbox column + select-all + bulk bar over the
// filtered rows — see DataTableSelection.tsx). Two pagination modes: client
// (default — caller passes ALL rows; filter/slice in memory) and server (caller
// passes ONE page + a `serverPagination` descriptor and drives search through
// `search.value`/`search.onChange`) for large lists that page on demand.
import { Fragment, useMemo, useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { DataTableToolbar } from "@/components/DataTableToolbar";
import { DataTableHead } from "@/components/DataTableHead";
import { RowSelectCell, useTableSelection } from "@/components/DataTableSelection";
import { TableBulkBar, usePageSelectAll } from "@/components/DataTableBulk";
import { Pagination } from "@/components/Pagination";
import { useDefaultPageSize } from "@/lib/preferences";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type {
  Column,
  FilterDef,
  ServerPagination,
  TableSelection,
} from "@/components/DataTable.types";
// Re-exported so call sites keep importing these from "@/components/DataTable".
export type { Column, FilterDef, ServerPagination, TableSelection };

interface Props<T> {
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
  /** When set, rows expand to a full-width detail sub-row (excludes onRowClick). */
  getRowDetail?: (row: T) => ReactNode;
  /** When set, a leading checkbox column + bulk action bar are rendered. */
  selection?: TableSelection<T>;
  /** Rows returning false get no checkbox + are excluded from bulk (default: all). */
  isSelectable?: (row: T) => boolean;
  pageSize?: number;
  /** When set, page on demand against the server instead of slicing in memory. */
  serverPagination?: ServerPagination;
  emptyMessage: string;
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  search,
  filters = [],
  onRowClick,
  getRowDetail,
  selection,
  isSelectable,
  pageSize,
  serverPagination,
  emptyMessage,
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
  const [page, setPage] = useState(1);
  // Page size: Settings default → `pageSize` prop → in-table override (reactive to Settings).
  const globalDefault = useDefaultPageSize();
  const [override, setOverride] = useState<number | null>(null);
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

  // Selection derives from the *filtered* set so bulk actions only touch visible
  // rows (in server mode that is the current page).
  const sel = useTableSelection(filtered, rowKey);

  const size = server ? server.pageSize : (override ?? pageSize ?? globalDefault);
  const total = server ? server.total : filtered.length;
  const pageCount = Math.max(1, Math.ceil(total / size));
  const safePage = server ? server.page : Math.min(page, pageCount);
  const pageRows = server ? filtered : filtered.slice((safePage - 1) * size, safePage * size);

  const canSelect = (r: T) => (isSelectable ? isSelectable(r) : true);
  // Header checkbox selects the CURRENT PAGE; TableBulkBar escalates to "all".
  const ps = usePageSelectAll({
    sel, pageRows, filtered, rowKey, canSelect, total,
    server: Boolean(server),
    resetKey: `${query}␟${JSON.stringify(filterVals)}`,
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
            else setPage(1);
          }}
          searchPlaceholder={search?.placeholder}
          filters={filters}
          filterVals={filterVals}
          onFilterChange={(key, v) => {
            setFilterVals((prev) => ({ ...prev, [key]: v }));
            setPage(1);
          }}
        />
      ) : null}

      {selection ? (
        <TableBulkBar selection={selection} ps={ps} selectedRows={sel.selectedRows} />
      ) : null}

      <div className="rounded-md border bg-card">
        <Table>
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
            {pageRows.length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={colCount} className="py-10 text-center text-muted-foreground">
                  {emptyMessage}
                </TableCell>
              </TableRow>
            ) : (
              pageRows.map((row) => {
                const key = rowKey(row);
                const isOpen = expanded.has(key);
                const clickable = expandable || Boolean(onRowClick);
                return (
                  <Fragment key={key}>
                    <TableRow
                      className={clickable ? "cursor-pointer" : undefined}
                      onClick={
                        expandable
                          ? () => toggleExpand(key)
                          : onRowClick
                            ? () => onRowClick(row)
                            : undefined
                      }
                    >
                      {selection ? (
                        <RowSelectCell
                          selectable={canSelect(row)}
                          checked={sel.keys.has(key)}
                          ariaLabel={selection.ariaSelectRow(row)}
                          onToggle={() => sel.toggle(key)}
                        />
                      ) : null}
                      {expandable ? (
                        <TableCell className="py-3 pr-0 text-muted-foreground">
                          {isOpen ? (
                            <ChevronDown className="size-4" />
                          ) : (
                            <ChevronRight className="size-4" />
                          )}
                        </TableCell>
                      ) : null}
                      {columns.map((c) => (
                        <TableCell key={c.key} className={cn("py-3", c.className)}>
                          {c.cell(row)}
                        </TableCell>
                      ))}
                    </TableRow>
                    {expandable && isOpen ? (
                      <TableRow className="hover:bg-transparent">
                        <TableCell colSpan={colCount} className="bg-muted/20 p-0">
                          {getRowDetail!(row)}
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </Fragment>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      <Pagination
        page={safePage}
        pageCount={pageCount}
        total={total}
        pageSize={size}
        onPageChange={server ? server.onPageChange : setPage}
        onPageSizeChange={
          server
            ? server.onPageSizeChange
            : (s) => {
                setOverride(s);
                setPage(1);
              }
        }
      />
    </div>
  );
}
