// frontend/src/components/skills/SkillDeliveryRow.tsx
// One agent's row on a skill's Delivery tab: a switch (delivered or not — it
// acts at once), the agent, where its copy stands, and the path or reason.
// A change in flight dims the row and says what is happening; an agent that
// cannot take a skill keeps its switch off and says why.
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { TruncatedText } from "@/components/ui/truncated-text";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import type { SkillDriftEntry } from "@/lib/api/skills";
import { isGranted, type AgentDelivery } from "@/lib/skills/delivery";
import type { StatusTone } from "@/lib/statusTone";
import { cn } from "@/lib/utils";

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

interface Props {
  agent: AgentOut;
  delivery: AgentDelivery;
  entry: SkillDriftEntry | undefined;
  /** A change to this agent is in flight, and which way. */
  pending?: "on" | "off";
  /** Why this agent cannot take the skill (its switch is disabled), if so. */
  blockedReason?: string;
  onToggle: (on: boolean) => void;
  onReview: (entry: SkillDriftEntry) => void;
}

export function SkillDeliveryRow({
  agent,
  delivery,
  entry,
  pending,
  blockedReason,
  onToggle,
  onReview,
}: Props) {
  const { t } = useTranslation();
  const { word, hint, path } = useStateText(delivery);
  const reviewable = delivery.state === "drift" && delivery.kind === "replaced_with_regular";
  const checked = pending ? pending === "on" : isGranted(delivery) && !blockedReason;
  const detail = pending
    ? t(pending === "on" ? "skills.delivery.delivering" : "skills.delivery.removing")
    : blockedReason
      ? blockedReason
      : hint;
  return (
    <li
      data-testid={`skill-delivery-${agent.name}`}
      aria-busy={pending ? true : undefined}
      className={cn(
        "grid grid-cols-[2.5rem_11rem_10rem_minmax(0,1fr)_auto] items-center gap-4 py-3",
        pending && "opacity-60",
      )}
    >
      <span className="flex items-center">
        {pending ? (
          <Loader2 className="size-4 animate-spin text-text-muted" aria-hidden />
        ) : (
          <Switch
            checked={checked}
            disabled={Boolean(blockedReason)}
            onCheckedChange={onToggle}
            aria-label={t("skills.delivery.switchLabel", { agent: agent.display_name })}
          />
        )}
      </span>
      <AgentBadge type={agent.type} name={agent.display_name} showName size="sm" />
      <StatusWord tone={stateTone(delivery)}>{word}</StatusWord>
      <span className="flex min-w-0 flex-col gap-0.5">
        {path ? (
          <TruncatedText
            mono
            text={abbreviateHomePath(path)}
            className="text-2xs text-text-muted"
          />
        ) : null}
        <TruncatedText text={detail} className="text-xs text-text-muted" />
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
