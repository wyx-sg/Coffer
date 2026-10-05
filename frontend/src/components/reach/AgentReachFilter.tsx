// src/components/reach/AgentReachFilter.tsx — a library list's reach filter (Skills, MCP servers, Custom tools):
// everything, or only what reaches one agent.
//
// It reads and writes the page's `?agent=` (lib/agents/agentFilter.ts), so the
// link from an agent's Skills or MCP servers tab lands with that agent already chosen here.
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AgentOption } from "@/components/agent/AgentOption";
import type { AgentFilter } from "@/lib/agents/agentFilter";
import { useSetAgentFilter } from "@/lib/agents/agentFilter";
import { agentDisplayName } from "@/lib/agents/display";
import { useAgents } from "@/lib/hooks/useAgents";

const ALL = "__all__";

export function AgentReachFilter({ filter }: { filter: AgentFilter | null }) {
  const { t } = useTranslation();
  const { data: agents = [] } = useAgents();
  const setAgent = useSetAgentFilter();
  const value = filter?.uid ?? ALL;
  return (
    <Select value={value} onValueChange={(v) => setAgent(v === ALL ? null : v)}>
      <SelectTrigger
        className="h-control-sm w-auto max-w-56 gap-1.5 text-xs"
        aria-label={t("reachFilter.label")}
      >
        <span className="text-text-muted">{t("reachFilter.label")}:</span>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{t("reachFilter.all")}</SelectItem>
        {agents.map((a) => (
          <SelectItem key={a.uid} value={a.uid}>
            <AgentOption type={a.type} name={agentDisplayName(a)} />
          </SelectItem>
        ))}
        {/* An `?agent=` that names no agent still shows, so the list never looks unfiltered. */}
        {filter && !agents.some((a) => a.uid === filter.uid) ? (
          <SelectItem value={filter.uid}>
            <AgentOption type="" name={filter.label ?? filter.uid} />
          </SelectItem>
        ) : null}
      </SelectContent>
    </Select>
  );
}
