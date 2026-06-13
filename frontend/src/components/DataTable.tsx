// frontend/src/components/DataTable.tsx
// The one reusable list table for every resource surface (Agents, MCP servers,
// Skills, …): search + filters + pagination, optional row click→detail, and an
// optional `selection` prop (checkbox column + select-all + bulk bar over the
// filtered rows — see DataTableSelection.tsx).
import { Fragment, useMemo, useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { DataTableToolbar } from "@/components/DataTableToolbar";
import {
  BulkBar,
  RowSelectCell,
  SelectAllHeadCell,
  useTableSelection,
} from "@/components/DataTableSelection";
import { Pagination } from "@/components/Pagination";
import { useDefaultPageSize } from "@/lib/preferences";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

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

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  /** When set, renders a search box filtering on this row→text accessor. */
  search?: { accessor: (row: T) => string; placeholder: string };
  filters?: FilterDef<T>[];
  onRowClick?: (row: T) => void;
  /** When set, rows expand to a full-width detail sub-row (excludes onRowClick). */
  getRowDetail?: (row: T) => ReactNode;
  /** When set, a leading checkbox column + bulk action bar are rendered. */
  selection?: TableSelection<T>;
  /** When set, rows for which this returns false are not selectable (no
   *  checkbox; excluded from select-all and bulk actions). Default: all
   *  selectable. Used to pin a non-deletable row (e.g. the built-in agent). */
  isSelectable?: (row: T) => boolean;
  pageSize?: number;
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
  emptyMessage,
}: Props<T>) {
  const [query, setQuery] = useState("");
  const [filterVals, setFilterVals] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  // Page size: Settings default → `pageSize` prop → in-table override (reactive to Settings).
  const globalDefault = useDefaultPageSize();
  const [override, setOverride] = useState<number | null>(null);
  const size = override ?? pageSize ?? globalDefault;
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

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (q && search && !search.accessor(row).toLowerCase().includes(q)) return false;
      for (const f of filters) {
        const v = filterVals[f.key];
        if (v && v !== "all" && f.accessor(row) !== v) return false;
      }
      return true;
    });
  }, [rows, query, filterVals, filters, search]);

  // Selection derives from the *filtered* set so bulk actions only touch visible rows.
  const sel = useTableSelection(filtered, rowKey);

  const pageCount = Math.max(1, Math.ceil(filtered.length / size));
  const safePage = Math.min(page, pageCount);
  const pageRows = filtered.slice((safePage - 1) * size, safePage * size);

  // Select-all spans the whole filtered set (across pages), not just this page,
  // and only the selectable rows (a pinned row may opt out via isSelectable).
  const filteredKeys = filtered.filter((r) => (isSelectable ? isSelectable(r) : true)).map(rowKey);
  const allSelected = filteredKeys.length > 0 && filteredKeys.every((k) => sel.keys.has(k));
  const someSelected = !allSelected && filteredKeys.some((k) => sel.keys.has(k));
  const hasToolbar = Boolean(search) || filters.length > 0;
  const showBulkBar = Boolean(selection) && sel.selectedRows.length > 0;

  return (
    <div className="space-y-4">
      {hasToolbar ? (
        <DataTableToolbar
          query={query}
          onQueryChange={(v) => {
            setQuery(v);
            setPage(1);
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

      {showBulkBar ? (
        <BulkBar
          label={selection!.bulkLabel(sel.selectedRows.length)}
          clearLabel={selection!.clearLabel}
          onClear={sel.clear}
        >
          {selection!.renderBulkActions({ selectedRows: sel.selectedRows, clear: sel.clear })}
        </BulkBar>
      ) : null}

      <div className="rounded-md border bg-card">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              {selection ? (
                <SelectAllHeadCell
                  checked={allSelected}
                  indeterminate={someSelected}
                  ariaLabel={selection.ariaSelectAll}
                  onToggle={() => sel.setMany(filteredKeys, !allSelected)}
                />
              ) : null}
              {expandable ? <TableHead className="h-10 w-8" /> : null}
              {columns.map((c) => (
                <TableHead key={c.key} className={cn("h-10", c.className)}>
                  {c.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
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
                        isSelectable && !isSelectable(row) ? (
                          <TableCell className="w-10" />
                        ) : (
                          <RowSelectCell
                            checked={sel.keys.has(key)}
                            ariaLabel={selection.ariaSelectRow(row)}
                            onToggle={() => sel.toggle(key)}
                          />
                        )
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
        total={filtered.length}
        pageSize={size}
        onPageChange={setPage}
        onPageSizeChange={(s) => {
          setOverride(s);
          setPage(1);
        }}
      />
    </div>
  );
}
