// frontend/src/components/DataTable.tsx
//
// The one reusable list table for every resource surface (Agents, MCP
// servers, and future kinds). It owns the search box, dropdown filter(s),
// and client-side pagination so each surface only declares columns + data.
// A row click navigates to that item's detail page; row actions are compact
// icon buttons that stopPropagation so they don't trigger the row click.
import { Fragment, useMemo, useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { Pagination } from "@/components/Pagination";
import { SearchInput } from "@/components/SearchInput";
import { useDefaultPageSize } from "@/lib/preferences";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  /** Stable key (also used for the React key). */
  key: string;
  header: ReactNode;
  /** Cell renderer for a row. */
  cell: (row: T) => ReactNode;
  /** Classes applied to both <th> and <td> (e.g. text-right for actions). */
  className?: string;
}

export interface FilterDef<T> {
  key: string;
  /** Placeholder shown on the trigger. */
  label: string;
  /** Label for the "no filter" option. */
  allLabel: string;
  options: { value: string; label: string }[];
  /** Value extracted from a row to compare against the selected option. */
  accessor: (row: T) => string;
}

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  /** When set, renders a search box filtering on this row→text accessor. */
  search?: { accessor: (row: T) => string; placeholder: string };
  filters?: FilterDef<T>[];
  onRowClick?: (row: T) => void;
  /**
   * When set, rows are expandable: a chevron column is prepended and clicking
   * a row toggles a full-width detail sub-row. Mutually exclusive with
   * onRowClick (expand takes precedence).
   */
  getRowDetail?: (row: T) => ReactNode;
  /** Initial rows-per-page. Defaults to the user's configured preference. */
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
  pageSize,
  emptyMessage,
}: Props<T>) {
  const [query, setQuery] = useState("");
  const [filterVals, setFilterVals] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  // Page size resolution, lowest-to-highest precedence:
  //   global Settings default → explicit `pageSize` prop → in-table override.
  // Following the reactive global default (rather than reading it once at
  // mount) means changing the size in Settings updates already-mounted tables
  // live; once the user picks a size in THIS table, that override sticks.
  const globalDefault = useDefaultPageSize();
  const [override, setOverride] = useState<number | null>(null);
  const size = override ?? pageSize ?? globalDefault;
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const expandable = Boolean(getRowDetail);
  const colCount = columns.length + (expandable ? 1 : 0);
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

  const pageCount = Math.max(1, Math.ceil(filtered.length / size));
  const safePage = Math.min(page, pageCount);
  const pageRows = filtered.slice((safePage - 1) * size, safePage * size);

  const hasToolbar = Boolean(search) || filters.length > 0;

  return (
    <div className="space-y-4">
      {hasToolbar ? (
        <div className="flex flex-wrap items-center gap-3">
          {search ? (
            <SearchInput
              value={query}
              onChange={(v) => {
                setQuery(v);
                setPage(1);
              }}
              placeholder={search.placeholder}
              ariaLabel={search.placeholder}
              className="w-full sm:max-w-xs"
            />
          ) : null}
          {filters.map((f) => (
            <Select
              key={f.key}
              value={filterVals[f.key] ?? "all"}
              onValueChange={(v) => {
                setFilterVals((prev) => ({ ...prev, [f.key]: v }));
                setPage(1);
              }}
            >
              <SelectTrigger aria-label={f.label} className="h-9 w-auto min-w-[8rem]">
                <SelectValue placeholder={f.label} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{f.allLabel}</SelectItem>
                {f.options.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ))}
        </div>
      ) : null}

      <div className="rounded-md border bg-card">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
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
