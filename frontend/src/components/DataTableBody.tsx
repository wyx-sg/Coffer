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
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-inset";

/** True when the key event started on a control that handles itself. */
function fromInteractiveChild(e: KeyboardEvent<HTMLTableRowElement>): boolean {
  return e.target !== e.currentTarget;
}

// Skeleton rows are shaped like the real ones (44 high, 10px bars, r4) and
// appear only after 300ms of waiting, so a fast answer never flashes them
// (Foundations-Tables "Loading", Shell-ListLoading). The header stays mounted.
const SKELETON_ROW =
  "hover:bg-transparent animate-in fade-in-0 fill-mode-both delay-300 duration-fast";

export function SkeletonRows({ count, colCount }: { count: number; colCount: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <TableRow key={`skeleton-${i}`} className={SKELETON_ROW} data-testid="skeleton-row">
          {Array.from({ length: colCount }, (_, j) => (
            <TableCell key={j}>
              <Skeleton className="h-2.5 w-full max-w-[140px]" />
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
    // Inside the table frame: the message as a 13/600 title, then its one
    // action (Foundations-Tables "Empty").
    <TableRow className="hover:bg-transparent">
      <TableCell colSpan={colCount} className="px-3 py-[18px] text-center">
        <div className="flex flex-col items-center gap-1.5">
          <p className="text-sm font-semibold text-text">{message}</p>
          {action ? <div className="mt-1">{action}</div> : null}
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
  isRowClickable?: (row: T) => boolean;
  rowFooter?: (row: T) => ReactNode;
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
  isRowClickable,
  rowFooter,
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
          : onRowClick && (isRowClickable?.(row) ?? true)
            ? () => onRowClick(row)
            : undefined;
        const footer = rowFooter?.(row);
        return (
          <Fragment key={key}>
            <TableRow
              className={cn(activate && ["cursor-pointer", ROW_FOCUS_CLASS])}
              // A ticked row reads as selected (surface-selected).
              data-state={selection && selectedKeys.has(key) ? "selected" : undefined}
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
                <TableCell className="pr-0 text-text-subtle">
                  {isOpen ? (
                    <ChevronDown className="size-4" />
                  ) : (
                    <ChevronRight className="size-4" />
                  )}
                </TableCell>
              ) : null}
              {columns.map((c) => (
                <TableCell key={c.key} className={c.className}>
                  {c.cell(row)}
                </TableCell>
              ))}
            </TableRow>
            {expandable && isOpen ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={colCount} className="bg-surface-sunken p-0">
                  {getRowDetail!(row)}
                </TableCell>
              </TableRow>
            ) : null}
            {footer ? (
              <TableRow className="hover:bg-transparent" data-row-footer={key}>
                <TableCell colSpan={colCount} className="px-4 pb-3 pt-0">
                  {footer}
                </TableCell>
              </TableRow>
            ) : null}
          </Fragment>
        );
      })}
    </>
  );
}
