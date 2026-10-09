// frontend/src/components/memory/MemoryAgentsTable.tsx
//
// This machine's agents on the Memory page (spec memory "Show each agent's own
// curation and ask it to curate now"): per agent, the copies Coffer wrote into
// it here (and how many the agent has since edited or removed — its own
// curation at work), whether its own memory and its own curation are on, with a
// hint to turn either on when it is not, and **Curate now**, which starts the
// agent without a terminal and asks it to consolidate its own memory. A writer
// that cannot write into the agent (its memory is off, a layout it does not
// recognise) says so in place of the copies.
import { Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { sortAgents } from "@/components/agent/agentOrder";
import { DataTable, type Column } from "@/components/DataTable";
import { StatusWord } from "@/components/status/StatusWord";
import { TableActionButton } from "@/components/table/TableActionButton";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { SyncAgent } from "@/lib/api/memoryTypes";
import { useCurateNow } from "@/lib/hooks/useMemory";
import type { StatusTone } from "@/lib/statusTone";

/** The two settings each agent's own memory has, per agent type. */
const KNOWN_TYPES = new Set(["claude_code", "codex"]);
const typeKey = (type: string) => (KNOWN_TYPES.has(type) ? type : "other");

const SWITCH_TONE: Record<string, StatusTone> = { on: "ok", off: "warn", unknown: "off" };
const switchWord = (value: string) => (value in SWITCH_TONE ? value : "unknown");

interface Props {
  agents: readonly SyncAgent[];
  isLoading?: boolean;
}

/** On / Off / Unknown, named for the agent's own setting ("Auto memory on"). */
function SwitchState({ type, setting, value }: { type: string; setting: string; value: string }) {
  const { t } = useTranslation();
  const word = switchWord(value);
  return (
    <StatusWord tone={SWITCH_TONE[word]}>
      {t(`memory.agents.${setting}.${typeKey(type)}.${word}`)}
    </StatusWord>
  );
}

function Copies({ agent }: { agent: SyncAgent }) {
  const { t } = useTranslation();
  const { writer, copies } = agent;
  if (writer.state !== "ok") {
    return (
      <div className="flex min-w-0 flex-col gap-0.5">
        <StatusWord tone={writer.state === "off" ? "off" : "warn"}>
          {t(`memory.agents.writer.${writer.state === "off" ? "off" : "blocked"}`)}
        </StatusWord>
        <span className="truncate text-xs text-text-muted">
          {[writer.reason, writer.path && abbreviateHomePath(writer.path)]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </div>
    );
  }
  const edited = copies.edited ?? 0;
  const removed = copies.removed ?? 0;
  const byAgent = [
    edited > 0 ? t("memory.agents.edited", { count: edited }) : null,
    removed > 0 ? t("memory.agents.removed", { count: removed }) : null,
  ].filter(Boolean);
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="text-sm tabular-nums">
        {t("memory.agents.written", { count: copies.written ?? 0 })}
      </span>
      {byAgent.length > 0 ? (
        <span className="text-xs text-text-muted">{byAgent.join(" · ")}</span>
      ) : null}
    </div>
  );
}

/** The hint under Curation: turn the agent's memory on first, then its curation. */
function curationHint(agent: SyncAgent): string | null {
  const type = typeKey(agent.agent_type);
  if (agent.curation.memory !== "on") return `memory.agents.hint.${type}.memory`;
  if (agent.curation.curation !== "on") return `memory.agents.hint.${type}.curation`;
  return null;
}

export function MemoryAgentsTable({ agents, isLoading = false }: Props) {
  const { t } = useTranslation();
  const curate = useCurateNow();
  const rows = sortAgents(agents.map((a) => ({ ...a, type: a.agent_type })));

  const columns: Column<SyncAgent>[] = [
    {
      key: "agent",
      header: t("memory.agents.cols.agent"),
      className: "w-[170px]",
      cell: (a) => (
        <AgentBadge type={a.agent_type} name={agentTypeLabel(a.agent_type)} size="sm" showName />
      ),
    },
    {
      key: "copies",
      header: t("memory.agents.cols.copies"),
      className: "w-[26%]",
      cell: (a) => <Copies agent={a} />,
    },
    {
      key: "memory",
      header: t("memory.agents.cols.memory"),
      className: "w-[150px]",
      cell: (a) => <SwitchState type={a.agent_type} setting="memory" value={a.curation.memory} />,
    },
    {
      key: "curation",
      header: t("memory.agents.cols.curation"),
      cell: (a) => {
        const hint = curationHint(a);
        return (
          <div className="flex min-w-0 flex-col gap-0.5">
            <SwitchState type={a.agent_type} setting="curation" value={a.curation.curation} />
            {hint ? <span className="text-xs text-text-muted">{t(hint)}</span> : null}
          </div>
        );
      },
    },
    {
      key: "actions",
      header: "",
      className: "w-[130px] text-right",
      cell: (a) => (
        <TableActionButton
          icon={Sparkles}
          label={t("memory.agents.curateNow")}
          aria-label={t("memory.agents.curateNowFor", { agent: agentTypeLabel(a.agent_type) })}
          disabled={
            a.curation.memory === "off" ||
            (curate.isPending && curate.variables?.type === a.agent_type)
          }
          onClick={() => curate.mutate({ type: a.agent_type, name: agentTypeLabel(a.agent_type) })}
        />
      ),
    },
  ];

  return (
    <DataTable
      fixed
      footer={false}
      rows={rows}
      isLoading={isLoading}
      columns={columns}
      rowKey={(a) => `${a.agent_type}:${a.agent}`}
      emptyMessage={t("memory.agents.empty")}
    />
  );
}
