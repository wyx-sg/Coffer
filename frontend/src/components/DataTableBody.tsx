// frontend/src/components/DataTableBody.tsx
// The three bodies a DataTable can show — skeleton rows while loading, the
// empty state, and the data rows themselves — kept out of DataTable.tsx so that
// file stays within its size budget. A data row with an action (row click or
// expand) is keyboard-operable: focusable, Enter/Space fire the same action a
// click does, and expandable rows announce their state via aria-expanded.
// Interactive children (checkbox, buttons, the reach control) keep stopping
// propagation so their clicks/keys never double as row navigation.
import { Fragment, type KeyboardEvent, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { RowSelectCell } from "@/components/DataTableSelection";
import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { Column, TableSelection } from "@/components/DataTable.types";

/** Visible focus for a focusable <tr>: an inset ring, since a row cannot
 *  offset a ring outside the table border. */
const ROW_FOCUS_CLASS =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset";

/** True when the key event started on a control that handles itself. */
function fromInteractiveChild(e: KeyboardEvent<HTMLTableRowElement>): boolean {
  return e.target !== e.currentTarget;
}

export function SkeletonRows({ count, colCount }: { count: number; colCount: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <TableRow key={`skeleton-${i}`} className="hover:bg-transparent" data-testid="skeleton-row">
          {Array.from({ length: colCount }, (_, j) => (
            <TableCell key={j} className="py-3">
              <Skeleton className="h-5 w-full max-w-xs" />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

export function EmptyRow({
  colCount,
  message,
  action,
}: {
  colCount: number;
  message: string;
  action?: ReactNode;
}) {
  return (
    <TableRow className="hover:bg-transparent">
      <TableCell colSpan={colCount} className="py-10 text-center text-sm text-muted-foreground">
        <div className="flex flex-col items-center gap-3">
          <p>{message}</p>
          {action ? <div>{action}</div> : null}
        </div>
      </TableCell>
    </TableRow>
  );
}

interface RowsProps<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  colCount: number;
  onRowClick?: (row: T) => void;
  getRowDetail?: (row: T) => ReactNode;
  expanded: Set<string>;
  onToggleExpand: (key: string) => void;
  selection?: TableSelection<T>;
  canSelect: (row: T) => boolean;
  selectedKeys: Set<string>;
  onToggleSelect: (key: string) => void;
}

export function DataRows<T>({
  rows,
  columns,
  rowKey,
  colCount,
  onRowClick,
  getRowDetail,
  expanded,
  onToggleExpand,
  selection,
  canSelect,
  selectedKeys,
  onToggleSelect,
}: RowsProps<T>) {
  const expandable = Boolean(getRowDetail);
  return (
    <>
      {rows.map((row) => {
        const key = rowKey(row);
        const isOpen = expanded.has(key);
        const activate = expandable
          ? () => onToggleExpand(key)
          : onRowClick
            ? () => onRowClick(row)
            : undefined;
        return (
          <Fragment key={key}>
            <TableRow
              className={cn(activate && ["cursor-pointer", ROW_FOCUS_CLASS])}
              tabIndex={activate ? 0 : undefined}
              aria-expanded={expandable ? isOpen : undefined}
              onClick={activate}
              onKeyDown={
                activate
                  ? (e) => {
                      if (fromInteractiveChild(e)) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        activate();
                      }
                    }
                  : undefined
              }
            >
              {selection ? (
                <RowSelectCell
                  selectable={canSelect(row)}
                  checked={selectedKeys.has(key)}
                  ariaLabel={selection.ariaSelectRow(row)}
                  onToggle={() => onToggleSelect(key)}
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
      })}
    </>
  );
}
