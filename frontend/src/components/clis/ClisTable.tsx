// src/components/clis/ClisTable.tsx — the CLIs list: one row per required command, problems first.
//
// Rows keep the daemon's order (missing, too old, not logged in, ready). Each
// shows the version found beside the minimum the skills ask for, the login
// state where the command declares one, and how many skills need it; a row
// opens `/clis/<command>`. The one row action is the problem's own remedy
// (CliActionButton): Install… / Update… open the confirmation, never a run.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { StatusWord } from "@/components/status/StatusWord";
import type { Cli } from "@/lib/api/clis";
import { cliTone } from "@/lib/clis/format";
import { CliActionButton } from "./CliActionButton";

interface Props {
  items: Cli[];
  isLoading: boolean;
  onInstall: (cli: Cli) => void;
}

export function ClisTable({ items, isLoading, onInstall }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const columns: Column<Cli>[] = [
    {
      key: "command",
      header: t("clis.cols.command"),
      cell: (cli) => (
        <div className="min-w-0">
          <span className="font-mono text-sm font-label">{cli.command}</span>
          <span className="ml-2 text-xs text-text-muted">
            {cli.path === null
              ? t("clis.notOnPath")
              : [cli.title, cli.path].filter(Boolean).join(" · ")}
          </span>
        </div>
      ),
    },
    {
      key: "version",
      header: t("clis.cols.version"),
      cell: (cli) => (
        <span className="whitespace-nowrap text-xs">
          <span className="font-mono">{cli.version ?? "—"}</span>
          {cli.min_version ? (
            <span className="ml-2 text-text-muted">
              {t("clis.needs", { version: cli.min_version })}
            </span>
          ) : null}
        </span>
      ),
    },
    {
      key: "login",
      header: t("clis.cols.login"),
      cell: (cli) => (
        <span className="text-xs text-text-muted">
          {cli.login.state && cli.login.state !== "not_needed"
            ? t(`clis.login.${cli.login.state}`)
            : "—"}
        </span>
      ),
    },
    {
      key: "neededBy",
      header: t("clis.cols.neededBy"),
      cell: (cli) => (
        <span className="text-xs">{t("clis.skillCount", { count: cli.needed_by.length })}</span>
      ),
    },
    {
      key: "status",
      header: t("clis.cols.status"),
      cell: (cli) => (
        <StatusWord tone={cliTone(cli.status)}>{t(`clis.status.${cli.status}`)}</StatusWord>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("clis.cols.actions")}</span>,
      className: "text-right",
      cell: (cli) => <CliActionButton cli={cli} onInstall={onInstall} table />,
    },
  ];

  return (
    <DataTable
      rows={items}
      columns={columns}
      rowKey={(cli) => cli.command}
      isLoading={isLoading}
      search={{
        accessor: (cli) => `${cli.command} ${cli.title ?? ""}`,
        placeholder: t("clis.search"),
      }}
      onRowClick={(cli) => navigate(`/clis/${encodeURIComponent(cli.command)}`)}
      emptyMessage={t("clis.empty.title")}
    />
  );
}
