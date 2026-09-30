// src/components/credentials/SecretsTable.tsx — one group of secrets (in use, or unused) as a table.
//
// Name (a standalone secret's name with the reference files cite; any other
// ref as itself; "Missing" when cited but not stored), what uses it, and the
// ⋯ menu. A destination waiting for approval and a value other local
// processes can read are marked beside the name.
import { KeyRound, TerminalSquare } from "lucide-react";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { StatusWord } from "@/components/status/StatusWord";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { CredentialRef } from "@/lib/api/credentials";
import { SecretRowMenu, type SecretRowAction } from "./SecretRowMenu";
import { SecretUsedBy } from "./SecretUsedBy";
import { displayName, hasPendingBinding } from "./secretRows";

interface Props {
  rows: CredentialRef[];
  isLoading?: boolean;
  emptyMessage: string;
  onAction: (action: SecretRowAction, row: CredentialRef) => void;
}

function NameCell({ row }: { row: CredentialRef }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-w-0 items-start gap-2">
      <KeyRound className="mt-0.5 size-3.5 shrink-0 text-text-muted" aria-hidden />
      <div className="min-w-0 space-y-0.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-mono text-xs text-text">{displayName(row)}</span>
          {!row.present ? <StatusWord tone="err">{t("secrets.row.missing")}</StatusWord> : null}
          {hasPendingBinding(row) ? (
            <StatusWord tone="warn">{t("secrets.row.pending")}</StatusWord>
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
        {row.uri ? <p className="truncate font-mono text-2xs text-text-subtle">{row.uri}</p> : null}
      </div>
    </div>
  );
}

export function SecretsTable({ rows, isLoading = false, emptyMessage, onAction }: Props) {
  const { t } = useTranslation();
  const columns: Column<CredentialRef>[] = [
    { key: "name", header: t("secrets.cols.name"), cell: (row) => <NameCell row={row} /> },
    {
      key: "usedBy",
      header: t("secrets.cols.usedBy"),
      className: "w-[260px]",
      cell: (row) => <SecretUsedBy row={row} />,
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
