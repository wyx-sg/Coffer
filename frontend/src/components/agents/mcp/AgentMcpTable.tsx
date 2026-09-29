// src/components/agents/mcp/AgentMcpTable.tsx — the MCP servers tab's table: Server · Command or gateway · Where · State · Owner · action.
//
// Board 2.1.23. A direct entry's name opens its read-only detail page under
// this tab; its row offers Adopt, or Remove duplicate when Coffer already
// serves an equivalent server. A Coffer server's row offers Manage, which opens
// the server's own page. Rows of a config file that failed to parse keep their
// actions disabled (board 2.1.27). Commands and paths wrap; nothing is cut.
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Import, Settings2, Trash2 } from "lucide-react";

import { DataTable, type Column } from "@/components/DataTable";
import { StatusWord } from "@/components/status/StatusWord";
import { TableActionButton } from "@/components/table/TableActionButton";
import { agentMcpEntryPath } from "@/lib/agents/routes";
import { entryCommand, type McpRow, type OwnMcpRow, type OwnMcpState } from "./mcpRows";

const STATE_LABEL: Record<OwnMcpState, string> = {
  bypasses: "agents.mcpTab.state.bypasses",
  duplicate: "agents.mcpTab.state.duplicate",
  readOnly: "agents.mcpTab.state.readOnly",
};

interface Props {
  agentType: string;
  rows: McpRow[];
  /** Whether the agent's Coffer connection has its gateway entry; undefined while unread. */
  connected: boolean | undefined;
  /** The file a direct entry sits in, as the Where column shows it. */
  whereLabel: (source: string) => string;
  onAdopt: (row: OwnMcpRow) => void;
  onRemoveDuplicate: (row: OwnMcpRow) => void;
}

export function AgentMcpTable({
  agentType,
  rows,
  connected,
  whereLabel,
  onAdopt,
  onRemoveDuplicate,
}: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const muted = "text-xs text-text-muted";

  const columns: Column<McpRow>[] = [
    {
      key: "server",
      header: t("agents.mcpTab.cols.server"),
      cell: (row) =>
        row.owner === "coffer" ? (
          <span className="break-all font-medium text-text">{row.name}</span>
        ) : (
          <div className="min-w-0 space-y-0.5">
            <Link
              to={agentMcpEntryPath(agentType, row.name, row.entry.source)}
              className="break-all font-medium text-text hover:underline"
            >
              {row.name}
            </Link>
            {row.entry.matches_resource !== null ? (
              <p className={muted}>
                {t("agents.mcpTab.duplicateOf", { name: row.entry.matches_resource })}
              </p>
            ) : row.entry.secret_keys.length > 0 ? (
              <p className={muted}>
                {t("agents.mcpTab.secretsInEnv", { count: row.entry.secret_keys.length })}
              </p>
            ) : null}
          </div>
        ),
    },
    {
      key: "command",
      header: t("agents.mcpTab.cols.command"),
      cell: (row) =>
        row.owner === "coffer" ? (
          <span className={muted}>{t("agents.mcpTab.gateway")}</span>
        ) : (
          <span className="break-all font-mono text-xs text-text">{entryCommand(row.entry)}</span>
        ),
    },
    {
      key: "where",
      header: t("agents.mcpTab.cols.where"),
      cell: (row) => (
        <span className="break-all font-mono text-xs text-text-muted">
          {row.owner === "coffer" ? t("agents.mcpTab.cofferEntry") : whereLabel(row.entry.source)}
        </span>
      ),
    },
    {
      key: "state",
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
          <div className="space-y-0.5">
            <StatusWord tone="warn">{t(STATE_LABEL[row.state])}</StatusWord>
            {row.state === "readOnly" ? (
              <p className={muted}>{t("agents.mcpTab.readOnlyReason")}</p>
            ) : null}
          </div>
        );
      },
    },
    {
      key: "owner",
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
      className: "text-right",
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
        return row.entry.matches_resource !== null ? (
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
        );
      },
    },
  ];

  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(row) => row.key}
      emptyMessage={t("agents.mcpTab.noMatch")}
    />
  );
}
