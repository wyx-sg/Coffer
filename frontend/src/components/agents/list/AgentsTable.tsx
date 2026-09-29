// src/components/agents/list/AgentsTable.tsx — spec agent-registry "List the supported agents as fixed rows on the Agents page".
//
// Always one row per supported type, in a fixed order, added or not: what it
// is and where its config lives, what reaches it through Coffer, its Coffer
// state with the one action that state calls for, and the ⋯ menu. The list
// has two rows, so there is no search, no selection and no bulk bar. An added
// row opens the agent; a row not added has no page to open.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { agentTabPath } from "@/lib/agents/routes";
import type { AgentRowState } from "@/lib/agents/rowState";
import type { AgentTypeOut } from "@/lib/api/agents";
import {
  ActionsCell,
  AgentNameCell,
  CofferCell,
  ConfigDirCell,
  CountCell,
  ModelCell,
} from "./AgentRowCells";
import { ConfigLeftBehindNotice } from "./ConfigLeftBehindNotice";

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
      cell: ({ row }) => <AgentNameCell row={row} />,
    },
    {
      key: "config",
      header: t("agents.list.col.configDir"),
      className: "w-[118px]",
      cell: ({ row }) => <ConfigDirCell row={row} />,
    },
    {
      key: "model",
      header: t("agents.list.col.model"),
      className: "w-[132px]",
      cell: ({ row }) => <ModelCell uid={row.uid} />,
    },
    {
      key: "skills",
      header: t("agents.list.col.skills"),
      className: "w-[44px]",
      cell: ({ row }) => <CountCell uid={row.uid} kind="skills" />,
    },
    {
      key: "mcp",
      header: t("agents.list.col.mcp"),
      className: "w-[44px]",
      cell: ({ row }) => <CountCell uid={row.uid} kind="mcp" />,
    },
    {
      key: "plugins",
      header: t("agents.list.col.plugins"),
      className: "w-[50px]",
      cell: ({ row }) => <CountCell uid={row.uid} kind="plugins" />,
    },
    {
      key: "coffer",
      header: t("agents.list.col.coffer"),
      className: "w-[172px]",
      cell: ({ row, state }) => <CofferCell row={row} state={state} />,
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("agents.list.col.actions")}</span>,
      className: "w-[128px] text-right",
      cell: ({ row }) => <ActionsCell row={row} />,
    },
  ];
  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={({ row }) => row.type}
      isLoading={isLoading}
      onRowClick={({ row }) => navigate(agentTabPath(row.type, "overview"))}
      isRowClickable={({ row }) => !!row.uid}
      rowFooter={({ row, state }) =>
        state === "config_left_behind" ? <ConfigLeftBehindNotice row={row} /> : null
      }
      emptyMessage={t("agents.list.empty")}
    />
  );
}
