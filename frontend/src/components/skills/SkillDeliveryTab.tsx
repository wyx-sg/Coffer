// frontend/src/components/skills/SkillDeliveryTab.tsx
// The Delivery tab: every registered agent, in Agents-page order, with where
// its copy of this skill stands — linked (with its path), copied, differing
// from master (only after Check again, which runs the read-only drift report),
// or not delivered and why. The rows are derived in lib/skills/delivery.ts;
// the reach control beside the heading is the same one the header carries,
// since reach is what decides who is in this list's "delivered" half.
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { sortAgents } from "@/components/agent/agentOrder";
import { EmptyState } from "@/components/EmptyState";
import { ScopeControl } from "@/components/ScopeControl";
import { StatusWord } from "@/components/status/StatusWord";
import type { StatusTone } from "@/components/status/statusTone";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SkillOut } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useKindReach } from "@/lib/hooks/useResources";
import { useCheckSkillCopies } from "@/lib/hooks/useSkills";
import { deliveryRows, type AgentDelivery } from "@/lib/skills/delivery";

function stateTone(d: AgentDelivery): StatusTone {
  if (d.state === "linked") return "ok";
  if (d.state === "notDelivered") return "off";
  return "warn";
}

function DeliveryState({ delivery }: { delivery: AgentDelivery }) {
  const { t } = useTranslation();
  let word: string;
  let detail: string;
  let path: string | null = null;
  switch (delivery.state) {
    case "linked":
      word = t("skills.delivery.state.linked");
      detail = t("skills.delivery.hint.linked");
      path = delivery.path;
      break;
    case "copied":
      word = t("skills.delivery.state.copied");
      detail = t("skills.delivery.hint.copied");
      path = delivery.path;
      break;
    case "drift":
      word = t(`skills.driftKind.${delivery.kind}`);
      detail = delivery.remedy;
      path = delivery.path;
      break;
    default:
      word = t("skills.delivery.state.notDelivered");
      detail = t(`skills.delivery.reason.${delivery.reason}`);
  }
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="flex min-w-0 flex-wrap items-center gap-2">
        <StatusWord tone={stateTone(delivery)}>{word}</StatusWord>
        {path ? (
          <span className="truncate font-mono text-xs text-text-muted">
            {abbreviateHomePath(path)}
          </span>
        ) : null}
      </span>
      <span className="text-xs text-text-muted">{detail}</span>
    </div>
  );
}

export function SkillDeliveryTab({ skill }: { skill: SkillOut }) {
  const { t } = useTranslation();
  const { data: agentsData } = useAgents();
  const agentReach = useKindReach("agent");
  const check = useCheckSkillCopies();
  const agents = sortAgents(agentsData ?? []);
  const rows = deliveryRows(
    skill,
    agents,
    (uid) => agentReach.get(uid)?.enabled ?? true,
    check.data?.entries ?? null,
  );
  const delivered = rows.filter(
    (r) => r.delivery.state === "linked" || r.delivery.state === "copied",
  ).length;

  return (
    <section className="flex flex-col gap-3" aria-label={t("skills.detail.tabs.delivery")}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{t("skills.detail.tabs.delivery")}</h3>
        <span className="text-xs text-text-muted">
          {t("skills.delivery.countOf", { delivered, total: agents.length })}
        </span>
        <span className="ml-auto inline-flex items-center gap-2">
          <ScopeControl kind="skill" uid={skill.uid} enabled={skill.enabled} scope={skill.scope} />
          <Button
            variant="outline"
            size="sm"
            onClick={() => check.mutate()}
            disabled={check.isPending}
          >
            <RefreshCw aria-hidden className={check.isPending ? "animate-spin" : undefined} />
            {check.isPending ? t("skills.delivery.checking") : t("skills.delivery.checkAgain")}
          </Button>
        </span>
      </div>

      {agents.length === 0 ? (
        <EmptyState title={t("scope.noAgents")} className="min-h-0 py-8" />
      ) : (
        <ul className="divide-y divide-border-subtle rounded-xl border border-border-subtle">
          {rows.map(({ agent, delivery }) => (
            <li
              key={agent.uid}
              data-testid={`skill-delivery-${agent.name}`}
              className="grid grid-cols-[10rem_minmax(0,1fr)] items-start gap-4 px-4 py-3"
            >
              <AgentBadge type={agent.type} name={agent.display_name} showName size="sm" />
              <DeliveryState delivery={delivery} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
