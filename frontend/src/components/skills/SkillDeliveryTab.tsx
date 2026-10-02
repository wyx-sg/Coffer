// frontend/src/components/skills/SkillDeliveryTab.tsx
// The Delivery tab (canvas 4.3.02, 4.3.41, 4.3.44): "Delivery · N of M agents"
// with Check again, then every registered agent in Agents-page order with
// where its copy of this skill stands — linked, copied where links aren't
// allowed, a folder in the way of Coffer's link (Review… opens the compare),
// or not delivered and why. The rows are derived in lib/skills/delivery.ts
// from the skill, the agents and the last Check copies report; Check again
// runs that read-only report afresh. Who gets the skill is the reach button
// in the header.
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { sortAgents } from "@/components/agent/agentOrder";
import { EmptyState } from "@/components/EmptyState";
import { StatusWord } from "@/components/status/StatusWord";
import type { StatusTone } from "@/lib/statusTone";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useKindReach } from "@/lib/hooks/useResources";
import { useSkillCopies } from "@/lib/hooks/useSkills";
import { deliveryRows, type AgentDelivery } from "@/lib/skills/delivery";

function stateTone(d: AgentDelivery): StatusTone {
  if (d.state === "linked" || d.state === "copied") return "ok";
  if (d.state === "notDelivered") return "off";
  return "warn";
}

/** The folder a path sits in, as the copied row names it ("~/.codex/skills"). */
function parentOf(path: string): string {
  return abbreviateHomePath(path.replace(/[\\/]+[^\\/]+[\\/]*$/, ""));
}

function useStateText(d: AgentDelivery): { word: string; hint: string; path: string | null } {
  const { t } = useTranslation();
  switch (d.state) {
    case "linked":
      return {
        word: t("skills.delivery.state.linked"),
        hint: t("skills.delivery.hint.linked"),
        path: d.path,
      };
    case "copied":
      return {
        word: t("skills.delivery.state.copied"),
        hint: t("skills.delivery.hint.copied", { dir: d.path ? parentOf(d.path) : "" }),
        path: d.path,
      };
    case "drift":
      return {
        word: t(`skills.driftKind.${d.kind}`),
        hint: t(`skills.delivery.drift.${d.kind}`, { path: abbreviateHomePath(d.path) }),
        path: d.path,
      };
    default:
      return {
        word: t("skills.delivery.state.notDelivered"),
        hint: t(`skills.delivery.reason.${d.reason}`),
        path: null,
      };
  }
}

function DeliveryRow({
  agent,
  delivery,
  entry,
  onReview,
}: {
  agent: { type: string; display_name: string; name: string };
  delivery: AgentDelivery;
  entry: SkillDriftEntry | undefined;
  onReview: (entry: SkillDriftEntry) => void;
}) {
  const { t } = useTranslation();
  const { word, hint, path } = useStateText(delivery);
  const reviewable = delivery.state === "drift" && delivery.kind === "replaced_with_regular";
  return (
    <li
      data-testid={`skill-delivery-${agent.name}`}
      className="grid grid-cols-[11rem_10rem_minmax(0,1fr)_auto] items-center gap-4 py-3"
    >
      <AgentBadge type={agent.type} name={agent.display_name} showName size="sm" />
      <StatusWord tone={stateTone(delivery)}>{word}</StatusWord>
      <span className="flex min-w-0 flex-col gap-0.5">
        {path ? (
          <span className="truncate font-mono text-2xs text-text-muted">
            {abbreviateHomePath(path)}
          </span>
        ) : null}
        <span className="text-xs text-text-muted">{hint}</span>
      </span>
      {reviewable && entry ? (
        <Button variant="outline" size="sm" onClick={() => onReview(entry)}>
          {t("skills.review")}
        </Button>
      ) : (
        <span />
      )}
    </li>
  );
}

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
  const delivered = rows.filter((r) => r.delivery.state !== "notDelivered").length;

  return (
    <section className="flex flex-col" aria-label={t("skills.detail.tabs.delivery")}>
      <div className="flex flex-wrap items-center gap-2 border-b border-border-subtle pb-2">
        <h3 className="text-sm font-semibold">{t("skills.detail.tabs.delivery")}</h3>
        <span className="text-xs text-text-muted">
          {t("skills.delivery.countOf", { delivered, total: agents.length })}
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
        <ul className="divide-y divide-border-subtle">
          {rows.map(({ agent, delivery }) => (
            <DeliveryRow
              key={agent.uid}
              agent={agent}
              delivery={delivery}
              entry={entries?.find(
                (e) => e.skill_name === skill.name && e.agent_name === agent.name,
              )}
              onReview={onReview}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
