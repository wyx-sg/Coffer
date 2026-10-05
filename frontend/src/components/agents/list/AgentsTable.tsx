// src/components/agents/list/AgentsTable.tsx — spec agent-registry "List the supported agents as fixed rows on the Agents page".
//
// Always one row per supported type, in a fixed order, added or not: what it
// is and where its config lives, what reaches it through Coffer, its Coffer
// state with the one action that state calls for, and the ⋯ menu. The columns
// are the Agents boards' fixed template (Agent takes the rest; Config 80,
// Provider 120, Model 112, counts 40/32/44, Coffer 172, Actions 140, ⋯ 26 with
// a 10px gap and 12px side padding): a fixed-layout table whose cells carry
// 5px each side, so every width below is the content width plus 10. The list
// has two rows, so there is no search, no selection and no bulk bar. An added
// row opens the agent; a row not added has no page to open.
import { Link, useNavigate } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { agentTabPath } from "@/lib/agents/routes";
import type { AgentRowState } from "@/lib/agents/rowState";
import type { AgentTypeOut } from "@/lib/api/agents";
import {
  ActionsCell,
  RowMenuCell,
  AgentNameCell,
  CofferCell,
  ConfigDirCell,
  CountCell,
  ModelCell,
  ProviderCell,
} from "./AgentRowCells";

const HELP_LINK = "text-accent-text underline-offset-2 hover:underline";

export interface AgentListRow {
  row: AgentTypeOut;
  state: AgentRowState | undefined;
}

interface Props {
  rows: AgentListRow[];
  isLoading: boolean;
}

export function AgentsTable({ rows, isLoading }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const columns: Column<AgentListRow>[] = [
    {
      key: "agent",
      header: t("agents.list.col.agent"),
      // Bounded: in an auto-layout table the one column without a width takes
      // the slack, and that is the config directory, not the name.
      className: "pl-3 pr-[5px]",
      cell: ({ row }) => <AgentNameCell row={row} />,
    },
    {
      key: "config",
      header: t("agents.list.col.configDir"),
      className: "px-[5px] w-[90px]",
      cell: ({ row }) => <ConfigDirCell row={row} />,
    },
    {
      key: "provider",
      header: t("agents.list.col.provider"),
      className: "px-[5px] w-[130px]",
      cell: ({ row }) => <ProviderCell uid={row.uid} />,
    },
    {
      key: "model",
      header: t("agents.list.col.model"),
      className: "px-[5px] w-[122px]",
      cell: ({ row }) => <ModelCell uid={row.uid} type={row.type} />,
    },
    {
      key: "skills",
      header: t("agents.list.col.skills"),
      className: "px-[5px] w-[50px]",
      cell: ({ row }) => <CountCell row={row} kind="skills" />,
    },
    {
      key: "mcp",
      header: t("agents.list.col.mcp"),
      className: "px-[5px] w-[42px]",
      cell: ({ row }) => <CountCell row={row} kind="mcp" />,
    },
    {
      key: "plugins",
      header: t("agents.list.col.plugins"),
      className: "px-[5px] w-[54px]",
      cell: ({ row }) => <CountCell row={row} kind="plugins" />,
    },
    {
      key: "coffer",
      header: t("agents.list.col.coffer"),
      className: "px-[5px] w-[182px]",
      cell: ({ row, state }) => <CofferCell row={row} state={state} />,
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("agents.list.col.actions")}</span>,
      className: "px-[5px] w-[150px] text-right",
      cell: ({ row }) => <ActionsCell row={row} />,
    },
    {
      key: "menu",
      header: <span className="sr-only">{t("agents.rowMenu.column")}</span>,
      className: "pl-[5px] pr-3 w-[43px] text-right",
      cell: ({ row }) => <RowMenuCell row={row} />,
    },
  ];
  return (
    <div className="flex flex-col gap-2">
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={({ row }) => row.type}
        isLoading={isLoading}
        onRowClick={({ row }) => navigate(agentTabPath(row.type, "overview"))}
        isRowClickable={({ row }) => !!row.uid}
        emptyMessage={t("agents.list.empty")}
        footer={false}
        fixed
      />
      {/* What the three counts mean, under the table rather than behind a "?" on one column.
          The pages it names are links: that is where reach is chosen. */}
      <p className="text-xs text-text-muted">
        <Trans
          i18nKey="agents.list.countsHelp"
          components={{
            mcp: <Link to="/mcp-servers" className={HELP_LINK} />,
            skills: <Link to="/skills" className={HELP_LINK} />,
          }}
        />
      </p>
    </div>
  );
}
