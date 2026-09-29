// frontend/src/components/agents/AgentStateBadges.tsx — spec agent-registry
// two-signal detection, as the agent pages show it.
//
// A registered agent whose program is not on this machine (`config_only` or
// `missing`) carries a "Not installed" badge — on its Agents-table row and in
// its detail header. The header also shows the version the program reports, as
// small secondary text beside the type chip.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type { AgentOut, DetectionState } from "@/lib/api/agents";
import { agentTypeLabel, isAgentInstalled } from "@/lib/agents/display";
import { toneClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";

/** "Not installed" when the program is absent; nothing otherwise. */
export function AgentNotInstalledBadge({ state }: { state: DetectionState | undefined }) {
  const { t } = useTranslation();
  if (isAgentInstalled(state)) return null;
  return (
    <Badge variant="outline" className={cn("border-transparent", toneClass("warn"))}>
      {t("agents.detection.notInstalled")}
    </Badge>
  );
}

/** The detail header's badges: type chip, "Not installed", version. */
export function AgentHeaderBadges({ agent }: { agent: AgentOut }) {
  return (
    <>
      <Badge variant="secondary">{agentTypeLabel(agent.type)}</Badge>
      <AgentNotInstalledBadge state={agent.state} />
      {agent.version ? (
        <span className="font-mono text-xs text-muted-foreground">{agent.version}</span>
      ) : null}
    </>
  );
}
