// frontend/src/components/skills/SkillDeliveryRow.tsx
// One agent's row on a skill's Delivery tab (canvas 4.3.06, 4.3.07): the agent,
// where its copy stands (Linked, Copied, Edited copy, Not delivered…) and the
// path with the one-line reason under it. Rows are read-only — who gets the
// skill is the Reach button's, and a folder in the way is reviewed from the
// banner above, not from here.
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { StatusWord } from "@/components/status/StatusWord";
import { TruncatedText } from "@/components/ui/truncated-text";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import type { AgentDelivery } from "@/lib/skills/delivery";
import type { StatusTone } from "@/lib/statusTone";

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
        word: t(`skills.delivery.driftWord.${d.kind}`),
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
  /** Why this agent cannot take the skill (switched off, not installed), if so. */
  blockedReason?: string;
}

export function SkillDeliveryRow({ agent, delivery, blockedReason }: Props) {
  const { word, hint, path } = useStateText(delivery);
  return (
    <li
      data-testid={`skill-delivery-${agent.name}`}
      className="grid grid-cols-[150px_150px_minmax(0,1fr)] items-start gap-3 border-t border-border-subtle py-3 last:border-b"
    >
      <span className="flex h-5 min-w-0 items-center">
        <AgentBadge type={agent.type} name={agent.display_name} showName size="sm" />
      </span>
      <span className="flex h-5 items-center">
        <StatusWord tone={stateTone(delivery)}>{word}</StatusWord>
      </span>
      <span className="flex min-w-0 flex-col gap-0.5">
        {path ? (
          <TruncatedText
            mono
            text={abbreviateHomePath(path)}
            className="text-xs leading-5 text-text"
          />
        ) : null}
        <TruncatedText
          text={delivery.state === "notDelivered" && blockedReason ? blockedReason : hint}
          className="text-xs text-text-muted"
        />
      </span>
    </li>
  );
}
