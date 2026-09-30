// src/components/agents/AgentHookEventCell.tsx — the Event cell of one Hooks-tab row.
//
// An agent's own hook sits on one event and shows it. Coffer's memory hook sits
// on several with one command, so its one row names itself — "Memory hook · 4
// events" — and follows with a chip per event (spec agent-registry "List every
// hook in the agent's native config").
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type { HookRow } from "@/lib/agents/hookRows";

export function AgentHookEventCell({ row }: { row: HookRow }) {
  const { t } = useTranslation();
  if (row.owner !== "coffer") {
    return <span className="font-mono text-xs text-text">{row.event}</span>;
  }
  return (
    <span className="flex flex-col gap-1">
      <span className="text-xs font-medium text-text">
        {t("agents.hooksTab.memoryHook", { count: row.events.length })}
      </span>
      <span className="flex flex-wrap gap-1">
        {row.events.map((event) => (
          <Badge key={event} variant="secondary" className="font-mono">
            {event}
          </Badge>
        ))}
      </span>
    </span>
  );
}
