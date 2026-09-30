// src/components/secret/SecretsTable.tsx — one group of secrets (in use, or unused) as a table.
//
// Name (a standalone secret's name; any other ref as itself), what uses it,
// when it was last used and created, and the ⋯ menu. Beside the name: "Missing
// on this Mac" for a ref this Mac has no value for — cited but not stored, or
// stored under another Mac's master key — whose Last used cell then offers Add
// value; "Waiting for approval" while a new value, or a new destination, waits
// in the Coffer app; and a mark for a value other local processes can read.
import { KeyRound, TerminalSquare } from "lucide-react";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { SecretRef } from "@/lib/api/secret";
import { SecretRowMenu, type SecretRowAction } from "./SecretRowMenu";
import { SecretUsedBy } from "./SecretUsedBy";
import { displayName, hasPendingBinding, isMissingHere } from "./secretRows";
import { lastUsedLabel, shortDate } from "./secretTimes";

interface Props {
  rows: SecretRef[];
  /** Refs whose new value, or whose adding, waits for approval. */
  waiting: ReadonlySet<string>;
  isLoading?: boolean;
  emptyMessage: string;
  onAction: (action: SecretRowAction, row: SecretRef) => void;
}

function NameCell({ row, waiting }: { row: SecretRef; waiting: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-w-0 items-center gap-2">
      <KeyRound className="size-3.5 shrink-0 text-text-muted" aria-hidden />
      <span className="truncate font-mono text-xs text-text">{displayName(row)}</span>
      {isMissingHere(row) ? (
        <Badge variant="destructive" className="rounded-full">
          {t("secrets.row.missing")}
        </Badge>
      ) : null}
      {waiting || hasPendingBinding(row) ? (
        <Badge variant="warning" className="rounded-full">
          {t("secrets.row.pending")}
        </Badge>
      ) : null}
      {row.readable_by_local_processes ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              tabIndex={0}
              aria-label={t("secrets.row.localReadable")}
              className="inline-flex text-text-subtle"
            >
              <TerminalSquare className="size-3.5" aria-hidden />
            </span>
          </TooltipTrigger>
          <TooltipContent className="max-w-[260px]">
            {t("secrets.row.localReadableHint")}
          </TooltipContent>
        </Tooltip>
      ) : null}
    </div>
  );
}

export function SecretsTable({ rows, waiting, isLoading = false, emptyMessage, onAction }: Props) {
  const { t, i18n } = useTranslation();
  const now = new Date();
  const columns: Column<SecretRef>[] = [
    {
      key: "name",
      header: t("secrets.cols.name"),
      cell: (row) => <NameCell row={row} waiting={waiting.has(row.ref)} />,
    },
    {
      key: "usedBy",
      header: t("secrets.cols.usedBy"),
      className: "w-[240px]",
      cell: (row) => <SecretUsedBy row={row} />,
    },
    {
      key: "lastUsed",
      header: t("secrets.cols.lastUsed"),
      className: "w-[120px]",
      cell: (row) =>
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
      header: t("secrets.cols.created"),
      className: "w-[88px]",
      cell: (row) => (
        <span className="text-xs text-text-muted">
          {row.created_at ? shortDate(row.created_at, i18n.language) : "—"}
        </span>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("secrets.cols.actions")}</span>,
      className: "w-[48px] text-right",
      cell: (row) => <SecretRowMenu row={row} onAction={onAction} />,
    },
  ];
  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(row) => row.ref}
      isLoading={isLoading}
      emptyMessage={emptyMessage}
    />
  );
}
