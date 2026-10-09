// frontend/src/components/memory/MemoryEntriesTable.tsx
//
// One project's memories (spec memory "Manage memory sync in the web UI"): each
// hub entry with its title and one-line description, its type, the agent and
// machine it came from, and — one column per agent on this machine — what
// became of its copy here: the origin itself, written, in Claude Code's rules
// file, waiting for the next sync, held back (the project is not checked out
// here), left to Codex's own import, or edited or removed by the agent's own
// curation. Read only: a memory's text is edited in the agent's own memory.
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { DataTable, type Column } from "@/components/DataTable";
import { StatusWord } from "@/components/status/StatusWord";
import { TruncatedText } from "@/components/ui/truncated-text";
import { agentTypeLabel } from "@/lib/agents/display";
import type { HubEntry } from "@/lib/api/memoryTypes";
import { copyState, copyStateTone } from "@/lib/memory/syncFacts";

interface Props {
  entries: HubEntry[];
  /** This machine's agent types, in Agents-page order: one copy column each. */
  agentTypes: readonly string[];
  /** This machine's id, so its own memories read "this machine". */
  machine: string;
  isLoading?: boolean;
}

function CopyCell({ raw }: { raw: string | undefined }) {
  const { t } = useTranslation();
  const state = copyState(raw);
  if (!state) return raw ? <StatusWord tone="off">{raw}</StatusWord> : null;
  return <StatusWord tone={copyStateTone(state)}>{t(`memory.copy.${state}`)}</StatusWord>;
}

export function MemoryEntriesTable({ entries, agentTypes, machine, isLoading = false }: Props) {
  const { t, i18n } = useTranslation();

  const columns: Column<HubEntry>[] = [
    {
      key: "memory",
      header: t("memory.entries.cols.memory"),
      className: "w-[34%]",
      cell: (e) => (
        <div className="flex min-w-0 flex-col gap-0.5">
          <TruncatedText text={e.title} className="text-sm font-medium" />
          {e.description ? (
            <TruncatedText text={e.description} className="text-xs text-text-muted" />
          ) : null}
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
      className: "w-[190px]",
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
    ...agentTypes.map(
      (type): Column<HubEntry> => ({
        key: `copy:${type}`,
        header: t("memory.entries.cols.copyIn", { agent: agentTypeLabel(type) }),
        className: "w-[150px]",
        cell: (e) => <CopyCell raw={e.copies[type]} />,
      }),
    ),
    {
      key: "updated",
      header: t("memory.entries.cols.updated"),
      className: "w-[110px] whitespace-nowrap",
      cell: (e) => (
        <span className="text-xs text-text-muted">
          {e.updated_at ? formatRelativeTime(e.updated_at, i18n.language) : null}
        </span>
      ),
    },
  ];

  return (
    <DataTable
      fixed
      rows={entries}
      isLoading={isLoading}
      columns={columns}
      search={{
        accessor: (e) => `${e.title} ${e.description} ${e.type}`,
        placeholder: t("memory.entries.search"),
      }}
      rowKey={(e) => e.id}
      emptyMessage={t("memory.entries.empty")}
    />
  );
}
