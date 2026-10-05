// frontend/src/components/memory/partitionFacts.tsx
//
// The small facts the partitions table and a partition's page both print
// (design 5.2.01 / 5.2.04, spec memory "Show a partition's memories read-only"):
// which agents a partition or a memory came from — "All agents" when that is
// every agent in play — and where its distilling stands.
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { agentTypeLabel } from "@/lib/agents/display";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import { agentTypeOfOrigin } from "./memoryAgents";

/** The distinct agent types behind a list of agent names, in a stable order. */
function types(agents: readonly string[]): string[] {
  return [...new Set(agents.map(agentTypeOfOrigin).filter(Boolean))].sort();
}

/** True when `agents` covers every agent in `everyone` (and there is more than one). */
function isAllAgents(agents: readonly string[], everyone: readonly string[]): boolean {
  const all = types(everyone);
  const mine = types(agents);
  return all.length > 1 && all.every((a) => mine.includes(a));
}

/** "All agents", or one badge per agent. */
export function AgentSources({
  agents,
  everyone,
}: {
  agents: readonly string[];
  everyone: readonly string[];
}) {
  const { t } = useTranslation();
  if (agents.length === 0) return null;
  if (isAllAgents(agents, everyone)) {
    return <span className="whitespace-nowrap text-xs text-text-muted">{t("memory.allAgents")}</span>;
  }
  return (
    <span className="inline-flex items-center gap-1">
      {types(agents).map((type) => (
        <AgentBadge key={type} type={type} name={agentTypeLabel(type)} size="sm" />
      ))}
    </span>
  );
}

/** Where a partition's distilling stands, as the Distil column reads it. */
export function distilState(
  t: ReturnType<typeof useTranslation>["t"],
  language: string,
  row: PartitionOut,
  running: boolean,
): string {
  if (running) return t("memory.distil.running");
  if (row.distilled_at) {
    return t("memory.distil.done", { when: formatRelativeTime(row.distilled_at, language) });
  }
  return t("memory.distil.never");
}
