// frontend/src/components/DataTableHead.tsx
// Header row for DataTable: the optional select-all checkbox, an optional
// expander spacer, and the column headers. Extracted so DataTable stays under
// the component line limit.
import { ArrowDown, ArrowUp } from "lucide-react";

import type { Column } from "@/components/DataTable";
import type { TableSort } from "@/components/DataTable.types";
import { SelectAllHeadCell } from "@/components/DataTableSelection";
import { TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

interface Props<T> {
  columns: Column<T>[];
  hasSelection: boolean;
  expandable: boolean;
  allSelected: boolean;
  someSelected: boolean;
  ariaSelectAll?: string;
  onToggleAll: () => void;
  sort?: TableSort | null;
  onSort?: (key: string) => void;
}

// Sticky so the column titles stay pinned while the body scrolls inside the
// height-capped table container. The head has no fill of its own
// (Foundations-Tables), so it carries the table's raised surface — solid, so
// scrolling rows don't bleed through.
const STICKY_HEAD = "sticky top-0 z-sticky bg-surface-raised";

export function DataTableHead<T>({
  columns,
  hasSelection,
  expandable,
  allSelected,
  someSelected,
  ariaSelectAll,
  onToggleAll,
  sort,
  onSort,
}: Props<T>) {
  return (
    <TableHeader>
      <TableRow className="group/row h-auto hover:bg-transparent">
        {hasSelection ? (
          <SelectAllHeadCell
            selecting={allSelected || someSelected}
            checked={allSelected}
            indeterminate={someSelected}
            ariaLabel={ariaSelectAll ?? ""}
            onToggle={onToggleAll}
            className={STICKY_HEAD}
          />
        ) : null}
        {expandable ? <TableHead className={cn("w-8", STICKY_HEAD)} /> : null}
        {columns.map((c) => (
          <TableHead
            key={c.key}
            className={cn(STICKY_HEAD, c.className)}
            aria-sort={
              c.sortable
                ? sort?.key === c.key
                  ? sort.dir === "asc"
                    ? "ascending"
                    : "descending"
                  : "none"
                : undefined
            }
          >
            {c.sortable ? <SortHeader column={c} sort={sort} onSort={onSort} /> : c.header}
          </TableHead>
        ))}
      </TableRow>
    </TableHeader>
  );
}

// A sortable header: plain text with an arrow once it is the active sort (11px, text
// colour); idle ones show the hover fill only. The button keeps the column's
// alignment so a right-aligned number column's label stays against its numbers.
function SortHeader<T>({
  column,
  sort,
  onSort,
}: {
  column: Column<T>;
  sort?: TableSort | null;
  onSort?: (key: string) => void;
}) {
  const active = sort?.key === column.key ? sort : null;
  const Arrow = active?.dir === "asc" ? ArrowUp : ArrowDown;
  const right = column.className?.includes("text-right");
  return (
    <button
      type="button"
      onClick={() => onSort?.(column.key)}
      className={cn(
        "-mx-1 inline-flex items-center gap-1 rounded-item px-1 py-0.5 hover:bg-surface-hover hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
        active ? "text-text" : null,
        right ? "flex-row-reverse" : null,
      )}
    >
      {column.header}
      {active ? <Arrow aria-hidden className="size-[11px]" /> : null}
    </button>
  );
}
