// src/components/secret/SecretsTable.tsx — the secrets as one table: checkbox, name, what uses it, when it was last used and created, and the row's actions.
//
// The checkbox column is always first and its header box selects every secret the filters show.
// Last used and Created are the only sortable columns (three clicks: newest first, oldest first,
// the default order); the sort lives in the URL (`?sort=last_used`). Only a batch of rows is in
// the DOM — DataTable shows the first `BATCH` and loads more on request — while the filters
// have already been applied to the whole set. A row with no value on this Mac offers Add value
// before its ⋯ menu.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type Column, type TableSort } from "@/components/DataTable";
import { RelativeTime } from "@/components/RelativeTime";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { SecretNameCell } from "./SecretNameCell";
import { SecretRowMenu, type SecretRowAction } from "./SecretRowMenu";
import { SecretUsedBy } from "./SecretUsedBy";
import type { SecretItem } from "./secretListView";
import { displayName } from "./secretRows";
import { shortDate } from "./secretTimes";

/** How many rows render at first, and each "Load more" adds. */
const BATCH = 50;

interface Props {
  /** The rows the filters keep, in the default order. */
  items: SecretItem[];
  sort: TableSort | null;
  onSortChange: (sort: TableSort | null) => void;
  selected: ReadonlySet<string>;
  onToggle: (ref: string, on: boolean) => void;
  onToggleAll: (on: boolean) => void;
  isLoading?: boolean;
  emptyMessage: string;
  emptyAction?: React.ReactNode;
  onAction: (action: SecretRowAction, row: SecretItem["row"]) => void;
}

export function SecretsTable({
  items,
  sort,
  onSortChange,
  selected,
  onToggle,
  onToggleAll,
  isLoading = false,
  emptyMessage,
  emptyAction,
  onAction,
}: Props) {
  const { t, i18n } = useTranslation();
  const ticked = items.filter((i) => selected.has(i.row.ref)).length;
  const columns = useMemo(() => {
    const cols: Column<SecretItem>[] = [
      {
        key: "select",
        header: (
          <Checkbox
            aria-label={t("secrets.selectAll")}
            checked={items.length > 0 && ticked === items.length}
            indeterminate={ticked > 0 && ticked < items.length}
            disabled={items.length === 0}
            onChange={(e) => onToggleAll(e.target.checked)}
          />
        ),
        className: "w-[44px]",
        cell: (item) => (
          <Checkbox
            checked={selected.has(item.row.ref)}
            onChange={(e) => onToggle(item.row.ref, e.target.checked)}
            aria-label={t("secrets.row.select", { name: item.short })}
          />
        ),
      },
      {
        key: "name",
        header: t("secrets.cols.name"),
        cell: (item) => <SecretNameCell item={item} />,
      },
      {
        key: "usedBy",
        header: t("secrets.cols.usedBy"),
        className: "w-[260px]",
        cell: (item) => <SecretUsedBy row={item.row} />,
      },
      {
        key: "last_used",
        header: t("secrets.cols.lastUsed"),
        className: "w-[112px]",
        sortable: true,
        sortValue: ({ row }) => row.last_used_at,
        cell: ({ row }) =>
          row.last_used_at ? (
            <RelativeTime iso={row.last_used_at} className="text-xs text-text-muted" />
          ) : (
            <span className="text-xs text-text-muted">{t("secrets.time.never")}</span>
          ),
      },
      {
        key: "created",
        header: t("secrets.cols.created"),
        className: "w-[88px]",
        sortable: true,
        sortValue: ({ row }) => row.created_at,
        cell: ({ row }) => (
          <span className="text-xs text-text-muted">
            {row.created_at ? shortDate(row.created_at, i18n.language) : "—"}
          </span>
        ),
      },
      {
        key: "actions",
        header: <span className="sr-only">{t("secrets.cols.actions")}</span>,
        className: "w-[150px] text-right",
        cell: (item) => (
          <div className="flex items-center justify-end gap-2">
            {item.missing ? (
              <Button
                variant="outline"
                size="sm"
                aria-label={t("secrets.row.addValueFor", { name: displayName(item.row) })}
                onClick={() => onAction("replace", item.row)}
              >
                {t("secrets.row.addValue")}
              </Button>
            ) : null}
            <SecretRowMenu row={item.row} onAction={onAction} />
          </div>
        ),
      },
    ];
    return cols;
  }, [t, i18n.language, items, ticked, selected, onToggle, onToggleAll, onAction]);

  return (
    <DataTable
      rows={items}
      columns={columns}
      rowKey={(item) => item.row.ref}
      isLoading={isLoading}
      pageSize={BATCH}
      fixed
      sort={sort}
      onSortChange={onSortChange}
      emptyMessage={emptyMessage}
      emptyAction={emptyAction}
    />
  );
}
