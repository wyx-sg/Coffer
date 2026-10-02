// frontend/src/components/DataTableSelection.tsx
// DataTable's row-selection concern, kept out of DataTable.tsx so that file
// stays within its size budget. Provides:
//   • useTableSelection — the selected-keys state + derived selected rows
//   • BulkBar          — the action bar shown while ≥1 row is selected
//   • SelectAllHeadCell / RowSelectCell — the checkbox cells
// Select-all operates on whatever keys the caller passes (DataTable passes the
// *filtered* keys), so "search/filter first, then select-all, then bulk-act"
// works as documented.
//
// The checkboxes stay out of sight until they are wanted: a row's shows while
// the pointer is over the row (or focus is in it), the header's while the
// pointer is over the header, and every one shows once any row is ticked.
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { X } from "lucide-react";

import { TableActionButton } from "@/components/table/TableActionButton";
import { Checkbox } from "@/components/ui/checkbox";
import { TableCell, TableHead } from "@/components/ui/table";
import { cn } from "@/lib/utils";

/**
 * Row-selection state for DataTable. `keys` is the persistent set of selected
 * row keys (kept across filter changes so a user can refine the filter without
 * losing prior picks). `visibleRows` is the *currently displayed* (filtered) set
 * — `selectedRows` is derived as selected ∩ visible so bulk actions only ever
 * operate on what's on screen, never on rows hidden by the active search/filter.
 */
export function useTableSelection<T>(visibleRows: T[], rowKey: (row: T) => string) {
  const [keys, setKeys] = useState<Set<string>>(new Set());

  const toggle = useCallback((key: string) => {
    setKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const setMany = useCallback((batch: string[], on: boolean) => {
    setKeys((prev) => {
      const next = new Set(prev);
      for (const k of batch) {
        if (on) next.add(k);
        else next.delete(k);
      }
      return next;
    });
  }, []);

  const clear = useCallback(() => setKeys(new Set()), []);

  // Selected ∩ visible: a selected row hidden by the current filter (or removed
  // upstream, e.g. deleted) silently drops out, so bulk actions act on exactly
  // the on-screen rows the user can see.
  const selectedRows = useMemo(
    () => visibleRows.filter((r) => keys.has(rowKey(r))),
    [visibleRows, keys, rowKey],
  );

  return { keys, toggle, setMany, clear, selectedRows };
}

export function BulkBar({
  label,
  clearLabel,
  onClear,
  children,
}: {
  label: string;
  clearLabel: string;
  onClear: () => void;
  children: ReactNode;
}) {
  // Foundations-Tables "Bulk bar": a 40px raised strip on the overlay shadow,
  // r10 — the count, the actions (safe first, destructive last), then Clear.
  return (
    <div className="flex min-h-10 flex-wrap items-center gap-2 rounded-xl bg-surface-raised py-[7px] pl-3 pr-2 shadow-overlay">
      <span className="mr-2 text-sm font-label text-text">{label}</span>
      {children}
      <TableActionButton icon={X} label={clearLabel} onClick={onClear} />
    </div>
  );
}

/** Hidden (but keeping its space) until hover/focus on the row, or while anything is ticked. */
const REVEAL =
  "opacity-0 transition-opacity duration-fast group-hover/row:opacity-100 group-focus-within/row:opacity-100 focus-within:opacity-100";

export function SelectAllHeadCell({
  checked,
  indeterminate,
  ariaLabel,
  onToggle,
  className,
  selecting = false,
}: {
  checked: boolean;
  /** Any row is ticked: the checkbox stays shown. */
  selecting?: boolean;
  indeterminate: boolean;
  ariaLabel: string;
  onToggle: () => void;
  className?: string;
}) {
  return (
    <TableHead className={cn("w-8", className)}>
      <span className={cn("inline-flex", !(selecting || checked || indeterminate) && REVEAL)}>
        <Checkbox
          checked={checked}
          indeterminate={indeterminate}
          aria-label={ariaLabel}
          onChange={onToggle}
        />
      </span>
    </TableHead>
  );
}

export function RowSelectCell({
  checked,
  ariaLabel,
  onToggle,
  selectable = true,
  selecting = false,
}: {
  checked: boolean;
  /** Any row is ticked: every checkbox stays shown. */
  selecting?: boolean;
  ariaLabel: string;
  onToggle: () => void;
  /** When false, render a spacer cell (no checkbox) to keep columns aligned. */
  selectable?: boolean;
}) {
  if (!selectable) return <TableCell className="w-8" />;
  return (
    <TableCell className="w-8" onClick={(e) => e.stopPropagation()}>
      <span className={cn("inline-flex", !(selecting || checked) && REVEAL)}>
        <Checkbox checked={checked} aria-label={ariaLabel} onChange={onToggle} />
      </span>
    </TableCell>
  );
}
