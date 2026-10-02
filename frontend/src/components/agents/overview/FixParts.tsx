// src/components/agents/overview/FixParts.tsx — the pieces both problem states share (boards 2.1.13, 2.1.14).
//
// A toned banner that says what is wrong with a Check again button, a "Ways to
// fix it" list of titled rows, and the right
// column's last-known configuration (model, provider, Coffer connection, last
// seen). Check again re-reads detection — the types query every agent page reads.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, RefreshCw } from "lucide-react";

import { STATUS_TONE, type StatusTone } from "@/lib/statusTone";
import { Button } from "@/components/ui/button";
import type { AgentOut } from "@/lib/api/agents";
import { useAgentConnection } from "@/lib/hooks/useAgents";
import { toneClass } from "@/lib/statusColors";
import { cn, formatDateTime } from "@/lib/utils";

import { InfoRow } from "./OverviewParts";
import { useDetectionCheck } from "./useDetectionCheck";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";
import { useProviderLabel } from "./useProviderLabel";

const K = "agents.overviewTab.problem";

function CheckAgainButton({ variant = "outline" }: { variant?: "outline" | "default" }) {
  const { t } = useTranslation();
  const { checking, check } = useDetectionCheck();
  return (
    <Button variant={variant} size="sm" onClick={check} disabled={checking}>
      <RefreshCw aria-hidden className={cn(checking && "animate-spin")} />
      {t(`${K}.checkAgain`)}
    </Button>
  );
}

export function ProblemBanner({
  tone,
  title,
  children,
}: {
  tone: StatusTone;
  title: string;
  children: ReactNode;
}) {
  return (
    <div
      role="status"
      className={cn(
        "flex items-start gap-2.5 rounded-lg px-3.5 py-3",
        toneClass(STATUS_TONE[tone]),
      )}
    >
      <AlertTriangle aria-hidden className="mt-px size-4 shrink-0" />
      <div className="flex min-w-0 grow flex-col gap-[3px]">
        <span className="text-sm font-medium text-text">{title}</span>
        <span className="text-xs leading-normal text-text-muted">{children}</span>
      </div>
      <span className="shrink-0 self-center">
        <CheckAgainButton />
      </span>
    </div>
  );
}

export function FixWay({
  title,
  body,
  children,
}: {
  title: string;
  body: string;
  children?: ReactNode;
}) {
  return (
    <li className="flex flex-wrap items-center gap-4 border-t border-border-subtle py-3">
      <div className="flex min-w-0 grow basis-64 flex-col gap-0.5">
        <span className="text-sm font-medium text-text">{title}</span>
        <span className="text-xs text-text-muted">{body}</span>
      </div>
      {children ? <span className="flex shrink-0 items-center gap-1.5">{children}</span> : null}
    </li>
  );
}

/** Model, Provider, Coffer and Last seen, as the agent was when Coffer last saw it. */
export function LastKnownRows({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const models = useFeatureEnabled("models") === true;
  const provider = useProviderLabel(agent);
  const connection = useAgentConnection(agent.uid);
  const word = connection.data ? t(`${K}.connectionWord.${connection.data.state}`) : undefined;
  return (
    <>
      <InfoRow label={t("agents.overviewTab.model.model")} mono={!!agent.model}>
        {agent.model ?? t("common.emptyValue")}
      </InfoRow>
      {models ? (
        <InfoRow label={t("agents.overviewTab.model.provider")}>
          {provider ?? t("common.emptyValue")}
        </InfoRow>
      ) : null}
      <InfoRow label={t(`${K}.coffer`)}>{word ?? t("common.emptyValue")}</InfoRow>
      <InfoRow label={t(`${K}.lastSeen`)}>{formatDateTime(agent.updated_at).slice(0, 16)}</InfoRow>
    </>
  );
}
