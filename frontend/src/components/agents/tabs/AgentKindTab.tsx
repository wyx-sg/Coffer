// src/components/agents/tabs/AgentKindTab.tsx — the search-and-list region of an agent's list tabs.
//
// Skills, MCP servers and Plugins share it (boards 2.1.20, 2.1.25, 2.1.31,
// shared empty 2.1.55): a search box (with an optional "?" beside it), an
// optional notice between the search and the list, then one bordered list of
// hairline rows the tab renders. A kind with nothing in it shows the same
// bordered box with a 13/600 title and one line, no icon, and keeps the search;
// a list that failed to load is the shared load-error row.
//
// A list whose rows can be acted on together passes `bulk`: a select-all box
// heads the list, each row takes a checkbox (`leading` of KindRow, handed to
// the children as `select`), and while any row is ticked the selection bar
// replaces the search row. Only what the search shows can be selected, so a
// bulk action never reaches a row the person cannot see.
import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ListSelectionBar } from "@/components/ListSelectionBar";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { SearchInput } from "@/components/SearchInput";
import { useTableSelection } from "@/components/DataTableSelection";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { TabEmpty } from "./TabEmpty";

/** What a row's checkbox needs: the box for a row, or a spacer when it cannot be ticked. */
export interface RowSelect<R> {
  leading: (row: R, name: string) => ReactNode;
}

interface BulkConfig<R> {
  rowKey: (row: R) => string;
  /** Rows that cannot be acted on in bulk (a read-only entry) take no checkbox. */
  selectable?: (row: R) => boolean;
  /** The bar's accessible name ("Selected skills"). */
  barLabel: string;
  /** The bar's actions, safe first and destructive last; `clear` empties the selection. */
  actions: (selected: R[], clear: () => void) => ReactNode;
}

interface Props<R> {
  rows: readonly R[];
  searchPlaceholder: string;
  /** The text a query is matched against, case-insensitively. */
  searchText: (row: R) => string;
  /** One `<li>` per visible row; the bordered `<ul>` around them is drawn here. */
  children: (visible: R[], select: RowSelect<R>) => ReactNode;
  bulk?: BulkConfig<R>;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** Shown in the bordered box when the kind holds nothing at all. */
  empty: { title: string; description: string };
  /** Sits right of the search box, e.g. a "?" HelpTip. */
  searchAside?: ReactNode;
  /** Between the search box and the list: a parse error, a missing program. */
  notice?: ReactNode;
  noMatch: string;
}

/** The frame every list of rows shares (Memory, Skills, MCP servers, Plugins). */
const LIST_FRAME = "overflow-hidden rounded-lg border border-border bg-surface-raised";

export function AgentKindTab<R>({
  rows,
  searchPlaceholder,
  searchText,
  children,
  bulk,
  isLoading = false,
  error,
  onRetry,
  empty,
  searchAside,
  notice,
  noMatch,
}: Props<R>) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((row) => !q || searchText(row).toLowerCase().includes(q));
  }, [rows, query, searchText]);

  const rowKey = bulk?.rowKey ?? ((row: R) => String(row));
  const selectableRows = useMemo(
    () => (bulk?.selectable ? visible.filter(bulk.selectable) : visible),
    [visible, bulk],
  );
  const selection = useTableSelection(selectableRows, rowKey);
  const selected = bulk ? selection.selectedRows : [];
  const selectedCount = selected.length;
  const allOn = selectableRows.length > 0 && selectedCount === selectableRows.length;

  const select: RowSelect<R> = {
    leading: (row, name) => {
      if (!bulk) return null;
      if (bulk.selectable && !bulk.selectable(row)) {
        return <span aria-hidden className="size-[15px] shrink-0" />;
      }
      const key = bulk.rowKey(row);
      return (
        <Checkbox
          checked={selection.keys.has(key)}
          aria-label={t("agents.kindTab.selectRow", { name })}
          onChange={() => selection.toggle(key)}
        />
      );
    },
  };

  let body: ReactNode;
  if (error && rows.length === 0) {
    body = <LoadErrorRow title={t("agents.kindTab.loadFailed")} error={error} onRetry={onRetry} />;
  } else if (isLoading && rows.length === 0) {
    body = <Skeleton className="h-28 w-full" aria-busy="true" />;
  } else if (rows.length === 0) {
    body = <TabEmpty title={empty.title} description={empty.description} />;
  } else if (visible.length === 0) {
    body = <p className="py-4 text-sm text-text-muted">{noMatch}</p>;
  } else {
    body = bulk ? (
      <div className={LIST_FRAME}>
        {selectableRows.length > 0 ? (
          <div className="flex items-center gap-3 border-b border-border-subtle bg-surface px-4 py-2">
            <Checkbox
              checked={allOn}
              indeterminate={selectedCount > 0 && !allOn}
              aria-label={t("agents.kindTab.selectAll")}
              onChange={() => selection.setMany(selectableRows.map(rowKey), !allOn)}
            />
            <span className="text-xs text-text-muted">{t("agents.kindTab.selectAll")}</span>
          </div>
        ) : null}
        <ul>{children(visible, select)}</ul>
      </div>
    ) : (
      <ul className={LIST_FRAME}>{children(visible, select)}</ul>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {bulk && selectedCount > 0 ? (
        <ListSelectionBar
          label={bulk.barLabel}
          count={selectedCount}
          total={selectableRows.length}
          onClear={selection.clear}
        >
          {bulk.actions(selected, selection.clear)}
        </ListSelectionBar>
      ) : (
        <div className="flex items-center gap-2">
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder={searchPlaceholder}
            ariaLabel={searchPlaceholder}
            className="w-60"
          />
          {searchAside}
        </div>
      )}
      {notice}
      {body}
    </div>
  );
}
