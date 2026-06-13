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
      <TableRow className="bg-muted/40 hover:bg-muted/40">
        {hasSelection ? (
          <SelectAllHeadCell
            checked={allSelected}
            indeterminate={someSelected}
            ariaLabel={ariaSelectAll ?? ""}
            onToggle={onToggleAll}
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
  );
}
