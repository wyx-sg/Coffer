// src/components/secret/SecretsTable.tsx — the secrets as one table: name and owner, what uses it, when it was last used and created, and the ⋯ menu.
//
// Name, Used by, Last used and Created sort (the header says which way). Only a batch of rows
// is in the DOM — DataTable shows the first `BATCH` and loads more on request — while the
// filters and the sort have already been applied to the whole set. A secret missing on this
// Mac offers Add value in its Last used cell. In the by-owner view the owner is the group's
// title, so the Used by column and the owner line leave.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import type { SecretListState, SortKey } from "@/lib/secrets/listState";
import { SecretNameCell } from "./SecretNameCell";
import { SecretRowMenu, type SecretRowAction } from "./SecretRowMenu";
import { SecretSortHeader } from "./SecretSortHeader";
import { SecretUsedBy } from "./SecretUsedBy";
import type { SecretItem } from "./secretListView";
import { displayName, isMissingHere } from "./secretRows";
import { lastUsedLabel, shortDate } from "./secretTimes";

/** How many rows render at first, and each "Load more" adds. */
export const BATCH = 50;

interface Props {
  items: SecretItem[];
  state: SecretListState;
  onSort?: (column: SortKey) => void;
  selected: ReadonlySet<string>;
  onToggle: (ref: string, on: boolean) => void;
  isLoading?: boolean;
  emptyMessage: string;
  /** In a by-owner group: no Used by column, no owner line, no sortable headers. */
  grouped?: boolean;
  onAction: (action: SecretRowAction, row: SecretItem["row"]) => void;
}

export function SecretsTable({
  items,
  state,
  onSort,
  selected,
  onToggle,
  isLoading = false,
  emptyMessage,
  grouped = false,
  onAction,
}: Props) {
  const { t, i18n } = useTranslation();
  const selecting = selected.size > 0;
  const columns = useMemo(() => {
    const now = new Date();
    const head = (column: SortKey, title: string) =>
      grouped || !onSort ? (
        title
      ) : (
        <SecretSortHeader column={column} title={title} state={state} onSort={onSort} />
      );
    const cols: Column<SecretItem>[] = [
      {
        key: "name",
        header: head("name", t("secrets.cols.name")),
        cell: (item) => (
          <SecretNameCell
            item={item}
            selecting={selecting}
            checked={selected.has(item.row.ref)}
            onCheckedChange={(on) => onToggle(item.row.ref, on)}
            hideOwner={grouped}
          />
        ),
      },
      {
        key: "usedBy",
        header: head("usedBy", t("secrets.cols.usedBy")),
        className: "w-[240px]",
        cell: (item) => <SecretUsedBy row={item.row} />,
      },
      {
        key: "lastUsed",
        header: head("lastUsed", t("secrets.cols.lastUsed")),
        className: "w-[120px]",
        cell: ({ row }) =>
          isMissingHere(row) ? (
            <Button
              variant="outline"
              size="sm"
              aria-label={t("secrets.row.addValueFor", { name: displayName(row) })}
              onClick={() => onAction("replace", row)}
            >
              {t("secrets.row.addValue")}
            </Button>
          ) : (
            <span className="text-xs text-text-muted">
              {lastUsedLabel(row.last_used_at, now, t, i18n.language)}
            </span>
          ),
      },
      {
        key: "created",
        header: head("created", t("secrets.cols.created")),
        className: "w-[88px]",
        cell: ({ row }) => (
          <span className="text-xs text-text-muted">
            {row.created_at ? shortDate(row.created_at, i18n.language) : "—"}
          </span>
        ),
      },
      {
        key: "actions",
        header: <span className="sr-only">{t("secrets.cols.actions")}</span>,
        className: "w-[48px] text-right",
        cell: ({ row }) => <SecretRowMenu row={row} onAction={onAction} />,
      },
    ];
    return grouped ? cols.filter((c) => c.key !== "usedBy") : cols;
  }, [t, i18n.language, state, onSort, selected, selecting, onToggle, grouped, onAction]);

  return (
    <DataTable
      // A new filter or sort starts again at the first batch.
      key={`${state.q}|${state.status}|${state.kind}|${state.sort}|${state.dir}`}
      rows={items}
      columns={columns}
      rowKey={(item) => item.row.ref}
      isLoading={isLoading}
      pageSize={BATCH}
      fixed
      emptyMessage={emptyMessage}
    />
  );
}
