// frontend/src/components/skills/SkillDeliveryTab.tsx
// The Delivery tab (canvas 4.3.02, 4.3.41, 4.3.44): "Delivery · N of M agents"
// with Check again, then every registered agent in Agents-page order with
// where its copy of this skill stands — linked, copied where links aren't
// allowed, a folder in the way of Coffer's link (Review… opens the compare),
// or not delivered and why. The rows are derived in lib/skills/delivery.ts
// from the skill, the agents and the last Check copies report; Check again
// runs that read-only report afresh. Each row's switch (and "All on / All
// off") edits who gets the skill — the same scope the header's reach button
// writes (useSkillDelivery), so the two stay in step.
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { sortAgents } from "@/components/agent/agentOrder";
import { EmptyState } from "@/components/EmptyState";
import { Section } from "@/components/Section";
import { SkillDeliveryRow } from "@/components/skills/SkillDeliveryRow";
import { Button } from "@/components/ui/button";
import type { AgentOut } from "@/lib/api/agents";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useKindReach } from "@/lib/hooks/useResources";
import { useSkillCopies } from "@/lib/hooks/useSkills";
import { useSkillDelivery } from "@/lib/hooks/useSkillDelivery";
import { deliveryRows } from "@/lib/skills/delivery";

interface Props {
  skill: SkillOut;
  onReview: (entry: SkillDriftEntry) => void;
}

export function SkillDeliveryTab({ skill, onReview }: Props) {
  const { t } = useTranslation();
  const { data: agentsData } = useAgents();
  const agentReach = useKindReach("agent");
  const copies = useSkillCopies();
  const agents = sortAgents(agentsData ?? []);
  const entries = copies.data?.entries ?? null;
  const rows = deliveryRows(skill, agents, (uid) => agentReach.get(uid)?.enabled ?? true, entries);
  const { pending, set, setAll } = useSkillDelivery(skill, agents);
  const busy = Object.keys(pending).length > 0;
  const blocked = (a: AgentOut): string | undefined => {
    if (agentReach.get(a.uid)?.enabled === false) return t("skills.delivery.reason.agentOff");
    if (a.state === "missing") return t("skills.delivery.reason.agentMissing");
    return undefined;
  };

  return (
    <Section
      title={t("skills.detail.tabs.delivery")}
      gap="snug"
      labelled
      actions={
        <span className="flex items-center gap-1">
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => void setAll(true)}>
            {t("skills.delivery.allOn")}
          </Button>
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => void setAll(false)}>
            {t("skills.delivery.allOff")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void copies.refetch()}
            disabled={copies.isFetching}
          >
            <RefreshCw aria-hidden className={copies.isFetching ? "animate-spin" : undefined} />
            {copies.isFetching ? t("skills.delivery.checking") : t("skills.delivery.checkAgain")}
          </Button>
        </span>
      }
    >
      {agents.length === 0 ? (
        <EmptyState title={t("scope.noAgents")} className="min-h-0 py-8" />
      ) : (
        <ul className="divide-y divide-border-subtle">
          {rows.map(({ agent, delivery }) => (
            <SkillDeliveryRow
              key={agent.uid}
              agent={agent}
              delivery={delivery}
              pending={pending[agent.uid]}
              blockedReason={blocked(agent)}
              onToggle={(on) => void set(agent, on)}
              entry={entries?.find(
                (e) => e.skill_name === skill.name && e.agent_name === agent.name,
              )}
              onReview={onReview}
            />
          ))}
        </ul>
      )}
    </Section>
  );
}
