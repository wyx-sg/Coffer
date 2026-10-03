// frontend/src/components/skills/SkillDeliveryTab.tsx
// The Delivery tab (canvas 4.3.06, 4.3.07): "Where each agent's copy of <name>
// stands. Checked 2 min ago." with Check again, then every registered agent in
// Agents-page order with where its copy stands — linked, copied where links
// aren't allowed, an edited copy (a folder in the way of Coffer's link), or not
// delivered and why. The rows are derived in lib/skills/delivery.ts from the
// skill, the agents and the last Check copies report; Check again runs that
// read-only report afresh. The tab only reads: who gets the skill is the Reach
// button's, and reviewing an edited copy is the banner's.
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { sortAgents } from "@/components/agent/agentOrder";
import { EmptyState } from "@/components/EmptyState";
import { SkillDeliveryRow } from "@/components/skills/SkillDeliveryRow";
import { Button } from "@/components/ui/button";
import type { AgentOut } from "@/lib/api/agents";
import type { SkillOut } from "@/lib/api/skills";
import { relativeTime } from "@/lib/clis/format";
import { useAgents } from "@/lib/hooks/useAgents";
import { useKindReach } from "@/lib/hooks/useResources";
import { useSkillCopies } from "@/lib/hooks/useSkills";
import { deliveryRows } from "@/lib/skills/delivery";

interface Props {
  skill: SkillOut;
}

export function SkillDeliveryTab({ skill }: Props) {
  const { t, i18n } = useTranslation();
  const { data: agentsData } = useAgents();
  const agentReach = useKindReach("agent");
  const copies = useSkillCopies();
  const agents = sortAgents(agentsData ?? []);
  const entries = copies.data?.entries ?? null;
  const rows = deliveryRows(skill, agents, (uid) => agentReach.get(uid)?.enabled ?? true, entries);
  const blocked = (a: AgentOut): string | undefined => {
    if (agentReach.get(a.uid)?.enabled === false) return t("skills.delivery.reason.agentOff");
    if (a.state === "missing") return t("skills.delivery.reason.agentMissing");
    return undefined;
  };
  const checked = copies.dataUpdatedAt
    ? ` ${t("skills.delivery.checked", {
        when: relativeTime(new Date(copies.dataUpdatedAt).toISOString(), i18n.language),
      })}`
    : "";

  return (
    <section className="flex flex-col" aria-label={t("skills.detail.tabs.delivery")}>
      <div className="flex min-h-control-sm items-center gap-2">
        <span className="text-xs text-text-muted">
          {t("skills.delivery.intro", { name: skill.name })}
          {checked}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto"
          onClick={() => void copies.refetch()}
          disabled={copies.isFetching}
        >
          <RefreshCw aria-hidden className={copies.isFetching ? "animate-spin" : undefined} />
          {copies.isFetching ? t("skills.delivery.checking") : t("skills.delivery.checkAgain")}
        </Button>
      </div>
      {agents.length === 0 ? (
        <EmptyState title={t("scope.noAgents")} className="min-h-0 py-8" />
      ) : (
        <ul>
          {rows.map(({ agent, delivery }) => (
            <SkillDeliveryRow
              key={agent.uid}
              agent={agent}
              delivery={delivery}
              blockedReason={blocked(agent)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
