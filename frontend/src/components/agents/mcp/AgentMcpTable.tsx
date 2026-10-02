// src/components/agents/mcp/AgentMcpTable.tsx — the MCP servers tab's table: Server · Command or gateway · Where · State · Owner · action.
//
// Board 2.1.23. A direct entry's name opens its read-only detail page under
// this tab; its row offers Adopt, or Remove duplicate when Coffer already
// serves an equivalent server. A Coffer server's row offers Manage, which opens
// the server's own page, as does its name (the page names this tab as the way back). Rows of a config file that failed to parse keep their
// actions disabled (board 2.1.27). Commands and paths wrap; nothing is cut.
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Import, Settings2, Trash2 } from "lucide-react";

import { DataTable, type Column } from "@/components/DataTable";
import { TruncatedText } from "@/components/ui/truncated-text";
import { StatusWord } from "@/components/status/StatusWord";
import { TableActionButton } from "@/components/table/TableActionButton";
import { entryCommand, type McpRow, type OwnMcpRow, type OwnMcpState } from "./mcpRows";

const STATE_LABEL: Record<OwnMcpState, string> = {
  bypasses: "agents.mcpTab.state.bypasses",
  duplicate: "agents.mcpTab.state.duplicate",
  readOnly: "agents.mcpTab.state.readOnly",
};

interface Props {
  rows: McpRow[];
  /** Whether the agent's Coffer connection has its gateway entry; undefined while unread. */
  connected: boolean | undefined;
  /** The file a direct entry sits in, as the Where column shows it. */
  whereLabel: (source: string) => string;
  onAdopt: (row: OwnMcpRow) => void;
  onRemoveDuplicate: (row: OwnMcpRow) => void;
  /** A direct entry's name: its JSON opens in a dialog. */
  onOpenEntry: (row: OwnMcpRow) => void;
}

export function AgentMcpTable({
  rows,
  connected,
  whereLabel,
  onAdopt,
  onRemoveDuplicate,
  onOpenEntry,
}: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const muted = "text-xs text-text-muted";

  const columns: Column<McpRow>[] = [
    {
      key: "server",
      className: "w-[24%]",
      header: t("agents.mcpTab.cols.server"),
      cell: (row) =>
        row.owner === "coffer" ? (
          <Link
            to={`/mcp-servers/${encodeURIComponent(row.name)}`}
            className="block min-w-0 font-medium text-text hover:underline"
          >
            <TruncatedText text={row.name} />
          </Link>
        ) : (
          <div className="min-w-0 space-y-0.5">
            <button
              type="button"
              onClick={() => onOpenEntry(row)}
              className="block w-full min-w-0 text-left font-medium text-text hover:underline"
            >
              <TruncatedText text={row.name} />
            </button>
            {row.entry.matches_resource !== null ? (
              <TruncatedText
                className={muted}
                text={t("agents.mcpTab.duplicateOf", { name: row.entry.matches_resource })}
              />
            ) : row.entry.secret_keys.length > 0 ? (
              <TruncatedText
                className={muted}
                text={t("agents.mcpTab.secretsInEnv", { count: row.entry.secret_keys.length })}
              />
            ) : null}
          </div>
        ),
    },
    {
      key: "command",
      className: "w-[26%]",
      header: t("agents.mcpTab.cols.command"),
      cell: (row) =>
        row.owner === "coffer" ? (
          <span className={muted}>{t("agents.mcpTab.gateway")}</span>
        ) : (
          <TruncatedText mono text={entryCommand(row.entry)} className="text-xs text-text" />
        ),
    },
    {
      key: "where",
      header: t("agents.mcpTab.cols.where"),
      cell: (row) => (
        <TruncatedText
          mono
          className="text-xs text-text-muted"
          text={
            row.owner === "coffer" ? t("agents.mcpTab.cofferEntry") : whereLabel(row.entry.source)
          }
        />
      ),
    },
    {
      key: "state",
      className: "w-[150px]",
      header: t("agents.mcpTab.cols.state"),
      cell: (row) => {
        if (row.owner === "coffer") {
          if (connected === undefined) return null;
          return connected ? (
            <StatusWord tone="ok">{t("agents.mcpTab.state.connected")}</StatusWord>
          ) : (
            <StatusWord tone="warn">{t("agents.mcpTab.state.notConnected")}</StatusWord>
          );
        }
        return (
          <div className="min-w-0 space-y-0.5">
            <StatusWord tone="warn">{t(STATE_LABEL[row.state])}</StatusWord>
            {row.state === "readOnly" ? (
              <TruncatedText className={muted} text={t("agents.mcpTab.readOnlyReason")} />
            ) : null}
          </div>
        );
      },
    },
    {
      key: "owner",
      className: "w-[84px]",
      header: t("agents.mcpTab.cols.owner"),
      cell: (row) => (
        <span className="whitespace-nowrap text-xs text-text-muted">
          {t(`agents.kindTab.owner.${row.owner}`)}
        </span>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("agents.mcpTab.cols.actions")}</span>,
      className: "w-[210px] text-right",
      cell: (row) => {
        if (row.owner === "coffer") {
          return (
            <TableActionButton
              icon={Settings2}
              label={t("agents.mcpTab.manage")}
              aria-label={`${t("agents.mcpTab.manage")}: ${row.name}`}
              onClick={() => navigate(`/mcp-servers/${encodeURIComponent(row.name)}`)}
            />
          );
        }
        const readOnly = row.state === "readOnly";
        return (
          <span className="inline-flex items-center justify-end gap-1">
            {row.entry.matches_resource !== null ? (
              <TableActionButton
                icon={Trash2}
                destructive
                disabled={readOnly}
                label={t("agents.mcpTab.removeDuplicate")}
                aria-label={`${t("agents.mcpTab.removeDuplicate")}: ${row.name}`}
                onClick={() => onRemoveDuplicate(row)}
              />
            ) : (
              <TableActionButton
                icon={Import}
                disabled={readOnly}
                label={t("agents.mcpTab.adopt")}
                aria-label={`${t("agents.mcpTab.adopt")}: ${row.name}`}
                onClick={() => onAdopt(row)}
              />
            )}
          </span>
        );
      },
    },
  ];

  return (
    <DataTable
      fixed
      rows={rows}
      columns={columns}
      rowKey={(row) => row.key}
      emptyMessage={t("agents.mcpTab.noMatch")}
    />
  );
}
