// frontend/src/components/DataTableSelection.tsx
// DataTable's row-selection concern, kept out of DataTable.tsx so that file
// stays within its size budget. Provides:
//   • useTableSelection — the selected-keys state + derived selected rows
//   • BulkBar          — the action bar shown while ≥1 row is selected
//   • SelectAllHeadCell / RowSelectCell — the checkbox cells
// Select-all operates on whatever keys the caller passes (DataTable passes the
// *filtered* keys), so "search/filter first, then select-all, then bulk-act"
// works as documented.
import { useCallback, useMemo, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
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
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/30 px-3 py-2">
      <span className="text-sm font-medium">{label}</span>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
      <Button variant="ghost" size="sm" className="ml-auto" onClick={onClear}>
        {clearLabel}
      </Button>
    </div>
  );
}

export function SelectAllHeadCell({
  checked,
  indeterminate,
  ariaLabel,
  onToggle,
  className,
}: {
  checked: boolean;
  indeterminate: boolean;
  ariaLabel: string;
  onToggle: () => void;
  className?: string;
}) {
  return (
    <TableHead className={cn("h-10 w-10", className)}>
      <Checkbox
        checked={checked}
        indeterminate={indeterminate}
        aria-label={ariaLabel}
        onChange={onToggle}
      />
    </TableHead>
  );
}

export function RowSelectCell({
  checked,
  ariaLabel,
  onToggle,
  selectable = true,
}: {
  checked: boolean;
  ariaLabel: string;
  onToggle: () => void;
  /** When false, render a spacer cell (no checkbox) to keep columns aligned. */
  selectable?: boolean;
}) {
  if (!selectable) return <TableCell className="w-10" />;
  return (
    <TableCell className="py-3" onClick={(e) => e.stopPropagation()}>
      <Checkbox checked={checked} aria-label={ariaLabel} onChange={onToggle} />
    </TableCell>
  );
}
