// src/components/agents/list/AgentsStatusLine.tsx — "2 agents · 1 connected · 1 needs repair" under the page title.
import { useTranslation } from "react-i18next";

import { StatusDot } from "@/components/status/StatusDot";
import { agentRowTone, type AgentRowState } from "@/lib/agents/rowState";

export function AgentsStatusLine({ states }: { states: (AgentRowState | undefined)[] }) {
  const { t } = useTranslation();
  const counts = new Map<AgentRowState, number>();
  for (const state of states) {
    if (state && state !== "checking") counts.set(state, (counts.get(state) ?? 0) + 1);
  }
  return (
    <span className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-muted">
      <span className="inline-flex items-center gap-1.5">
        <StatusDot tone="off" />
        {t("agents.list.count", { count: states.length })}
      </span>
      {[...counts].map(([state, count]) => (
        <span key={state} className="inline-flex items-center gap-1.5">
          <StatusDot tone={agentRowTone(state)} />
          {t(`agents.list.statusCount.${state}`, { count })}
        </span>
      ))}
    </span>
  );
}
