// frontend/src/components/DataTableBulk.tsx
// Page-vs-all selection on top of useTableSelection, plus the escalation banner
// and bulk-action bar. Split out of DataTableSelection.tsx to keep both files
// within the component size budget.
//
// The header checkbox toggles the rows RENDERED (the whole list, or its first
// 100 when it is longer); when all of them are selected and more rows match,
// SelectAllBar offers escalation to "select all matching" — every filtered key.
import { useTranslation } from "react-i18next";

import type { TableSelection } from "@/components/DataTable.types";
import { ListSelectionBar } from "@/components/ListSelectionBar";
import { Button } from "@/components/ui/button";

export interface PageSelectAll {
  pageAllSelected: boolean;
  pageSomeSelected: boolean;
  togglePage: () => void;
  banner: "offer" | "active" | null;
  selectAll: () => void;
  clearAll: () => void;
  /** Bulk-bar count: the full total once all-matching / all-loaded is active. */
  count: number;
  total: number;
}

interface SelectionState<T> {
  keys: Set<string>;
  setMany: (keys: string[], on: boolean) => void;
  clear: () => void;
  selectedRows: T[];
}

export function usePageSelectAll<T>(opts: {
  sel: SelectionState<T>;
  pageRows: T[];
  filtered: T[];
  rowKey: (r: T) => string;
  canSelect: (r: T) => boolean;
  total: number;
  /** When this changes (search/filter), the all-matching escalation resets. */
  resetKey: string;
}): PageSelectAll {
  const { sel } = opts;
  const pageKeys = opts.pageRows.filter(opts.canSelect).map(opts.rowKey);
  const pageAllSelected = pageKeys.length > 0 && pageKeys.every((k) => sel.keys.has(k));
  const pageSomeSelected = !pageAllSelected && pageKeys.some((k) => sel.keys.has(k));
  const moreBeyondPage = opts.total > opts.pageRows.length;

  const allLoadedKeys = opts.filtered.filter(opts.canSelect).map(opts.rowKey);
  const allLoadedSelected = allLoadedKeys.length > 0 && allLoadedKeys.every((k) => sel.keys.has(k));

  const togglePage = () => {
    sel.setMany(pageKeys, !pageAllSelected);
  };
  const selectAll = () => sel.setMany(allLoadedKeys, true);
  const clearAll = () => sel.clear();

  const active = allLoadedSelected && moreBeyondPage;
  const banner: "offer" | "active" | null = active
    ? "active"
    : pageAllSelected && moreBeyondPage
      ? "offer"
      : null;

  return {
    pageAllSelected,
    pageSomeSelected,
    togglePage,
    banner,
    selectAll,
    clearAll,
    count: active ? opts.total : sel.selectedRows.length,
    total: opts.total,
  };
}

function SelectAllBar({
  state,
  total,
  onSelectAll,
  onClear,
}: {
  state: "offer" | "active";
  total: number;
  onSelectAll: () => void;
  onClear: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-surface-sunken px-3 py-1.5 text-xs text-muted-foreground">
      {state === "offer" ? (
        <>
          <span>{t("common.bulk.pageSelected")}</span>
          <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={onSelectAll}>
            {t("common.bulk.selectAllMatching", { count: total })}
          </Button>
        </>
      ) : (
        <>
          <span>{t("common.bulk.allSelected", { count: total })}</span>
          <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={onClear}>
            {t("common.clear")}
          </Button>
        </>
      )}
    </div>
  );
}

/** The selection escalation banner + bulk-action bar (ListSelectionBar). */
export function TableBulkBar<T>({
  selection,
  ps,
  selectedRows,
}: {
  selection: TableSelection<T>;
  ps: PageSelectAll;
  selectedRows: T[];
}) {
  const { t } = useTranslation();
  const show = selectedRows.length > 0;
  return (
    <>
      {ps.banner ? (
        <SelectAllBar
          state={ps.banner}
          total={ps.total}
          onSelectAll={ps.selectAll}
          onClear={ps.clearAll}
        />
      ) : null}
      {show ? (
        <ListSelectionBar
          label={t("common.bulk.bar")}
          count={ps.count}
          total={ps.total}
          onClear={ps.clearAll}
        >
          {selection.renderBulkActions({
            selectedRows,
            clear: ps.clearAll,
          })}
        </ListSelectionBar>
      ) : null}
    </>
  );
}
