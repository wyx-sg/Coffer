// src/components/ListSelectionBar.tsx — the one bulk bar (Foundations 0.6.02), for tables and lists alike.
//
// While rows are ticked it replaces the page's filter row: a floating bar (40
// high, r10, overlay shadow) reading "N of M selected", a divider, the caller's
// actions — safe first, destructive last, in the danger look — and Clear
// (ghost). There is no select-all here: the header box does that. Esc clears
// the selection, unless a dialog or menu is open over the page.
import { useEffect, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

interface Props {
  /** The bar's accessible name ("Selected skills"). */
  label: string;
  count: number;
  /** How many rows the page lists (after filters); without it the bar reads "N selected". */
  total?: number;
  onClear: () => void;
  /** The list's bulk actions (reach, delete). */
  children?: ReactNode;
}

export function ListSelectionBar({ label, count, total, onClear, children }: Props) {
  const { t } = useTranslation();
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (document.querySelector('[role="dialog"], [role="alertdialog"], [role="menu"]')) return;
      onClear();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClear]);
  return (
    <div
      role="region"
      aria-label={label}
      className="flex min-h-10 flex-wrap items-center gap-2 rounded-xl border border-border-subtle bg-surface-raised py-[7px] pl-3 pr-2 shadow-overlay"
    >
      <span className="text-sm font-label text-text">
        {total === undefined
          ? t("common.bulk.selected", { count })
          : t("common.bulk.selectedOf", { count, total })}
      </span>
      <span aria-hidden className="mx-1 h-4 w-px bg-border" />
      {children}
      <Button variant="ghost" size="sm" onClick={onClear}>
        {t("common.clear")}
      </Button>
    </div>
  );
}
