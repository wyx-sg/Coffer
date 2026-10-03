// src/components/agents/list/AgentsTable.tsx — spec agent-registry "List the supported agents as fixed rows on the Agents page".
//
// Always one row per supported type, in a fixed order, added or not: what it
// is and where its config lives, what reaches it through Coffer, its Coffer
// state with the one action that state calls for, and the ⋯ menu. The list
// has two rows, so there is no search, no selection and no bulk bar. An added
// row opens the agent; a row not added has no page to open.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { HelpTip } from "@/components/HelpTip";
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
      className: "w-[240px] max-w-[260px]",
      cell: ({ row }) => <AgentNameCell row={row} />,
    },
    {
      key: "config",
      header: t("agents.list.col.configDir"),
      className: "min-w-[140px]",
      cell: ({ row }) => <ConfigDirCell row={row} />,
    },
    {
      key: "model",
      header: t("agents.list.col.model"),
      className: "w-[160px]",
      cell: ({ row }) => <ModelCell uid={row.uid} type={row.type} />,
    },
    {
      key: "skills",
      header: (
        <span className="inline-flex items-center gap-1.5">
          {t("agents.list.col.skills")}
          <HelpTip label={t("agents.list.countsLabel")}>{t("agents.list.countsHelp")}</HelpTip>
        </span>
      ),
      className: "w-[44px]",
      cell: ({ row }) => <CountCell row={row} kind="skills" />,
    },
    {
      key: "mcp",
      header: t("agents.list.col.mcp"),
      className: "w-[44px]",
      cell: ({ row }) => <CountCell row={row} kind="mcp" />,
    },
    {
      key: "plugins",
      header: t("agents.list.col.plugins"),
      className: "w-[44px]",
      cell: ({ row }) => <CountCell row={row} kind="plugins" />,
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
      emptyMessage={t("agents.list.empty")}
      footer={false}
    />
  );
}
