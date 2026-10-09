// frontend/src/components/memory/MemoryProjectsTable.tsx
//
// The hub's projects (spec memory "Manage memory sync in the web UI and on the command line"): global
// memories first — written into every agent on every machine — then one row per
// project with where it is checked out on this machine (a project that is not
// is held back: its memories wait in the hub), how many memories it holds and
// which agents they came from. A row opens the project's memories. Read only:
// there is no status, reach or selection, and nothing here edits a memory.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { sortAgents } from "@/components/agent/agentOrder";
import { DataTable, type Column } from "@/components/DataTable";
import { StatusWord } from "@/components/status/StatusWord";
import { TruncatedPath, TruncatedText } from "@/components/ui/truncated-text";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { SyncProject } from "@/lib/api/memoryTypes";
import { projectPath } from "@/lib/memory/syncFacts";

/** A project row, or the global memories' row (`global`, key `""`). */
type Row = SyncProject & { global?: boolean };

interface Props {
  projects: readonly SyncProject[];
  globalMemories: number;
  isLoading?: boolean;
}

/** One badge per agent the memories came from, each with how many. */
function Origins({ agents }: { agents: Record<string, number> }) {
  const types = sortAgents(Object.keys(agents).map((type) => ({ type })));
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {types.map(({ type }) => (
        <span key={type} className="inline-flex items-center gap-1 text-xs text-text-muted">
          <AgentBadge type={type} name={agentTypeLabel(type)} size="sm" />
          <span className="tabular-nums">{agents[type]}</span>
        </span>
      ))}
    </span>
  );
}

export function MemoryProjectsTable({ projects, globalMemories, isLoading = false }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const rows: Row[] = [
    ...(globalMemories > 0
      ? [
          {
            key: "",
            folder: "",
            memories: globalMemories,
            agents: {},
            checked_out: null,
            global: true,
          },
        ]
      : []),
    ...projects,
  ];

  const columns: Column<Row>[] = [
    {
      key: "project",
      header: t("memory.projects.cols.project"),
      className: "w-[34%]",
      cell: (r) =>
        r.global ? (
          <span className="text-sm font-medium">{t("memory.projects.global")}</span>
        ) : (
          <TruncatedText text={r.key} className="font-mono text-xs font-medium" />
        ),
    },
    {
      key: "here",
      header: t("memory.projects.cols.here"),
      cell: (r) =>
        r.global ? (
          <span className="text-xs text-text-muted">{t("memory.projects.everywhere")}</span>
        ) : r.checked_out ? (
          <TruncatedPath
            text={abbreviateHomePath(r.checked_out)}
            className="font-mono text-2xs text-text-muted"
          />
        ) : (
          <StatusWord tone="off">{t("memory.projects.notHere")}</StatusWord>
        ),
    },
    {
      key: "memories",
      header: t("memory.projects.cols.memories"),
      className: "w-[96px] whitespace-nowrap text-right",
      cell: (r) => <span className="tabular-nums">{r.memories}</span>,
    },
    {
      key: "from",
      header: t("memory.projects.cols.from"),
      className: "w-[180px]",
      cell: (r) => <Origins agents={r.agents} />,
    },
  ];

  return (
    <DataTable
      fixed
      rows={rows}
      isLoading={isLoading}
      columns={columns}
      search={{
        accessor: (r) => `${r.key} ${r.checked_out ?? ""}`,
        placeholder: t("memory.projects.search"),
      }}
      rowKey={(r) => (r.global ? "global" : r.key)}
      onRowClick={(r) => navigate(projectPath(r.global ? null : r))}
      emptyMessage={t("memory.projects.empty")}
    />
  );
}
