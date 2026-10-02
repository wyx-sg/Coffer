// frontend/src/components/DataTableHead.tsx
// Header row for DataTable: the optional select-all checkbox, an optional
// expander spacer, and the column headers. Extracted so DataTable stays under
// the component line limit.
import type { Column } from "@/components/DataTable";
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
          <TableHead key={c.key} className={cn(STICKY_HEAD, c.className)}>
            {c.header}
          </TableHead>
        ))}
      </TableRow>
    </TableHeader>
  );
}
