// src/components/agents/overview/FixParts.tsx — the pieces both problem states share (boards 2.1.13, 2.1.14).
//
// A toned banner that says what is wrong with a Check again button, a "Ways to
// fix it" list of titled rows, the install command to copy, and the right
// column's last-known configuration (model, provider, Coffer connection, last
// seen). Check again re-reads detection — the types query every agent page reads.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Copy, RefreshCw } from "lucide-react";

import { STATUS_TONE, type StatusTone } from "@/components/status/statusTone";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import type { AgentOut } from "@/lib/api/agents";
import { useAgentConnection } from "@/lib/hooks/useAgents";
import { toneClass } from "@/lib/statusColors";
import { cn, formatDateTime } from "@/lib/utils";

import { InfoRow } from "./OverviewSection";
import { useDetectionCheck } from "./useDetectionCheck";
import { useProviderLabel } from "./useProviderLabel";

const K = "agents.overviewTab.problem";

export function CheckAgainButton({ variant = "outline" }: { variant?: "outline" | "default" }) {
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

export function InstallCommand({ command }: { command: string }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const copy = () =>
    void navigator.clipboard
      ?.writeText(command)
      .then(() => toast.success(t("common.copied")))
      .catch(() => undefined);
  return (
    <>
      <code className="break-all font-mono text-xs text-text">{command}</code>
      <Button variant="ghost" size="icon-sm" onClick={copy} aria-label={t(`${K}.copyCommand`)}>
        <Copy aria-hidden />
      </Button>
    </>
  );
}

/** Model, Provider, Coffer and Last seen, as the agent was when Coffer last saw it. */
export function LastKnownRows({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const provider = useProviderLabel(agent.type);
  const connection = useAgentConnection(agent.uid);
  const word = connection.data ? t(`${K}.connectionWord.${connection.data.state}`) : undefined;
  return (
    <>
      <InfoRow label={t("agents.overviewTab.model.model")} mono={!!agent.model}>
        {agent.model ?? t("common.emptyValue")}
      </InfoRow>
      <InfoRow label={t("agents.overviewTab.model.provider")}>
        {provider ?? t("common.emptyValue")}
      </InfoRow>
      <InfoRow label={t(`${K}.coffer`)}>{word ?? t("common.emptyValue")}</InfoRow>
      <InfoRow label={t(`${K}.lastSeen`)}>{formatDateTime(agent.updated_at).slice(0, 16)}</InfoRow>
    </>
  );
}
