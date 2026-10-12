// frontend/src/components/memory/MemoryList.tsx
//
// The open scope's memories, beside the scope list (spec memory "Manage memory
// sync in the web UI and on the command line"). The header names the scope —
// global memories, or a project with its full key and where it is checked out
// here (or that it is not, so its memories wait in the hub) — and the list
// below shows each memory: its title and one-line description, its type, the
// agent and machine it came from, and when it last changed. A copy state shows
// on a row only when it is worth a look (waiting for the next sync, edited or
// removed by the agent's own curation); a written copy says nothing. Search,
// type and source filter the list (the table's own toolbar). A row opens the memory in the drawer.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { sortAgents } from "@/components/agent/agentOrder";
import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { DataTable, type Column } from "@/components/DataTable";
import { StatusWord } from "@/components/status/StatusWord";
import { TruncatedText } from "@/components/ui/truncated-text";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { HubEntry, SyncProject } from "@/lib/api/memoryTypes";
import { notableCopies, projectName } from "@/lib/memory/syncFacts";

interface Props {
  /** The open project, or `null` for global memories. */
  project: SyncProject | null;
  count: number;
  entries: HubEntry[];
  /** This machine's id, so its own memories read "this machine". */
  machine: string;
  isLoading?: boolean;
  onOpen: (entry: HubEntry) => void;
  /** The source filter the list opens with (`?source=`, from an agent's Memory tab). */
  source?: string | null;
}

/** What a row calls out about its copies: one quiet word per agent. */
function Notes({ copies }: { copies: Record<string, string> }) {
  const { t } = useTranslation();
  const notes = notableCopies(copies);
  if (notes.length === 0) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-0.5">
      {notes.map(([agent, state]) => (
        <StatusWord key={agent} tone={state === "pending" ? "off" : "warn"} className="text-2xs">
          {t(`memory.note.${state}`, { agent: agentTypeLabel(agent) })}
        </StatusWord>
      ))}
    </span>
  );
}

export function MemoryList({
  project,
  count,
  entries,
  machine,
  isLoading = false,
  onOpen,
  source = null,
}: Props) {
  const { t, i18n } = useTranslation();
  const types = useMemo(() => [...new Set(entries.map((e) => e.type))].sort(), [entries]);
  const sources = useMemo(
    () =>
      sortAgents([...new Set(entries.map((e) => e.origin_agent))].map((type) => ({ type }))).map(
        (a) => a.type,
      ),
    [entries],
  );

  const columns: Column<HubEntry>[] = [
    {
      key: "memory",
      header: t("memory.entries.cols.memory"),
      cell: (e) => (
        <div className="flex min-w-0 flex-col gap-0.5">
          <TruncatedText text={e.title} className="text-sm font-medium" />
          {e.description ? (
            <TruncatedText text={e.description} className="text-xs text-text-muted" />
          ) : null}
          <Notes copies={e.copies} />
        </div>
      ),
    },
    {
      key: "type",
      header: t("memory.entries.cols.type"),
      className: "w-[96px]",
      cell: (e) => <span className="text-xs text-text-muted">{e.type}</span>,
    },
    {
      key: "origin",
      header: t("memory.entries.cols.origin"),
      className: "w-[170px]",
      cell: (e) => (
        <span className="inline-flex min-w-0 items-center gap-1.5">
          <AgentBadge type={e.origin_agent} name={agentTypeLabel(e.origin_agent)} size="sm" />
          <TruncatedText
            text={e.origin_machine === machine ? t("memory.entries.thisMachine") : e.origin_machine}
            className="text-xs text-text-muted"
          />
        </span>
      ),
    },
    {
      key: "updated",
      header: t("memory.entries.cols.updated"),
      className: "w-[96px] whitespace-nowrap",
      cell: (e) => (
        <span className="text-xs text-text-muted">
          {e.updated_at ? formatRelativeTime(e.updated_at, i18n.language) : null}
        </span>
      ),
    },
  ];

  const where = project ? (
    project.checked_out ? (
      <span className="font-mono text-xs">{abbreviateHomePath(project.checked_out)}</span>
    ) : (
      t("memory.detail.notHere")
    )
  ) : (
    t("memory.detail.global")
  );

  return (
    <div className="flex flex-col gap-4" data-testid="memory-list">
      <header className="flex min-w-0 flex-col gap-1">
        <h2 className="text-lg font-semibold">
          {project ? projectName(project.key) : t("memory.projects.global")}
        </h2>
        <p className="flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-text-muted">
          {project ? <span className="font-mono">{project.key}</span> : null}
          {project ? <span aria-hidden>·</span> : null}
          <span>{where}</span>
          <span aria-hidden>·</span>
          <span>{t("memory.detail.memories", { count })}</span>
        </p>
      </header>
      <DataTable
        fixed
        rows={entries}
        isLoading={isLoading}
        columns={columns}
        search={{
          accessor: (e) => `${e.title} ${e.description}`,
          placeholder: t("memory.entries.search"),
        }}
        initialFilters={source ? { source } : undefined}
        filters={[
          {
            key: "type",
            label: t("memory.entries.filters.type"),
            options: types.map((v) => ({ value: v, label: v })),
            accessor: (e) => e.type,
          },
          {
            key: "source",
            label: t("memory.entries.filters.source"),
            options: sources.map((v) => ({ value: v, label: agentTypeLabel(v) })),
            accessor: (e) => e.origin_agent,
          },
        ]}
        rowKey={(e) => e.id}
        onRowClick={onOpen}
        emptyMessage={t("memory.entries.empty")}
      />
    </div>
  );
}
