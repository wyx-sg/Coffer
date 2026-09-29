// src/components/agent/AgentBadgeGroup.tsx — a set of chosen agents shown as a row of small badges.
//
// Each chosen agent is an sm badge, 4 apart, in Agents-page order. When every
// agent is chosen the row says the words "All agents" instead, even when every
// badge would fit (Foundations-AgentBadge "Groups").
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import { AgentBadge, type AgentBadgeState } from "./AgentBadge";
import { sortAgents } from "./agentOrder";

interface AgentBadgeGroupItem {
  type: string;
  name?: string;
  state?: AgentBadgeState;
}

interface AgentBadgeGroupProps {
  agents: AgentBadgeGroupItem[];
  /** How many agents exist; when every one is chosen the group reads "All agents". */
  total?: number;
  className?: string;
}

export function AgentBadgeGroup({ agents, total, className }: AgentBadgeGroupProps) {
  const { t } = useTranslation();
  if (total !== undefined && total > 0 && agents.length >= total) {
    return <span className={cn("text-sm text-text", className)}>{t("agentBadge.allAgents")}</span>;
  }
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      {sortAgents(agents).map((a, i) => (
        <AgentBadge
          key={`${a.type}:${a.name ?? ""}:${i}`}
          type={a.type}
          name={a.name}
          state={a.state}
          size="sm"
        />
      ))}
    </span>
  );
}
