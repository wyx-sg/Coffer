// frontend/src/components/DataCardGrid.tsx
//
// The card-grid sibling of DataTable: a reusable list surface that owns the
// search box, dropdown filter(s), and client-side pagination, but renders each
// row as a free-form card in a responsive grid rather than a table row. Each
// surface only declares its data + a per-row card renderer. A card click
// navigates to that item's detail page (when onCardClick is set); inner
// buttons/toggles must stopPropagation so they don't trigger the card click.
import { useMemo, useState, type ReactNode } from "react";

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
import { cn } from "@/lib/utils";
// Reuse the table's FilterDef so a surface can share one filter definition
// between its table and card views without redeclaring it.
import type { FilterDef } from "@/components/DataTable";

export type { FilterDef };

interface Props<T> {
  rows: T[];
  rowKey: (row: T) => string;
  /** Renders the body of one card. */
  renderCard: (row: T) => ReactNode;
  /** When set, renders a search box filtering on this row→text accessor. */
  search?: { accessor: (row: T) => string; placeholder: string };
  filters?: FilterDef<T>[];
  /** Initial cards-per-page. Defaults to the user's configured preference. */
  pageSize?: number;
  emptyMessage: string;
  /**
   * When set, each card is clickable (cursor-pointer + role=button) and a click
   * calls this. Inner controls must stopPropagation to avoid triggering it.
   */
  onCardClick?: (row: T) => void;
}

export function DataCardGrid<T>({
  rows,
  rowKey,
  renderCard,
  search,
  filters = [],
  pageSize,
  emptyMessage,
  onCardClick,
}: Props<T>) {
  const [query, setQuery] = useState("");
  const [filterVals, setFilterVals] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  // Page size resolution mirrors DataTable: global Settings default → explicit
  // `pageSize` prop → in-grid override. Following the reactive global default
  // means a Settings change updates already-mounted grids live; once the user
  // picks a size in THIS grid, that override sticks.
  const globalDefault = useDefaultPageSize();
  const [override, setOverride] = useState<number | null>(null);
  const size = override ?? pageSize ?? globalDefault;

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

      {pageRows.length === 0 ? (
        <div className="rounded-md border bg-card py-10 text-center text-muted-foreground">
          {emptyMessage}
        </div>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {pageRows.map((row) => {
            const key = rowKey(row);
            if (onCardClick) {
              return (
                <div
                  key={key}
                  role="button"
                  tabIndex={0}
                  className={cn("cursor-pointer focus-visible:outline-none")}
                  onClick={() => onCardClick(row)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onCardClick(row);
                    }
                  }}
                >
                  {renderCard(row)}
                </div>
              );
            }
            return <div key={key}>{renderCard(row)}</div>;
          })}
        </div>
      )}

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
