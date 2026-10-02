// src/components/ListSelectionBar.tsx — the selection bar both resource lists (MCP servers, Skills) show at the top of their column while rows are ticked.
//
// It takes the filter rows' place: a select-all box (indeterminate when only
// some of the listed rows are ticked), "Selected N", the list's own bulk
// actions as children, and Clear.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

interface Props {
  /** The bar's accessible name ("Selected skills"). */
  label: string;
  /** The select-all box's accessible name. */
  selectAllLabel: string;
  count: number;
  /** Every selectable row the current filters show is ticked. */
  allChecked: boolean;
  onToggleAll: (on: boolean) => void;
  onClear: () => void;
  /** The list's bulk actions (reach, delete). */
  children?: ReactNode;
}

export function ListSelectionBar({
  label,
  selectAllLabel,
  count,
  allChecked,
  onToggleAll,
  onClear,
  children,
}: Props) {
  const { t } = useTranslation();
  return (
    <div
      role="region"
      aria-label={label}
      className="flex flex-wrap items-center gap-2 rounded-lg bg-surface-sunken py-1.5 pl-3 pr-1.5"
    >
      <Checkbox
        checked={allChecked}
        indeterminate={!allChecked}
        onChange={(e) => onToggleAll(e.target.checked)}
        aria-label={selectAllLabel}
      />
      <span className="mr-auto text-xs font-label text-text">
        {t("common.bulk.selected", { count })}
      </span>
      {children}
      <Button variant="ghost" size="sm" onClick={onClear}>
        {t("common.clear")}
      </Button>
    </div>
  );
}
