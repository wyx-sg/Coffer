// src/components/agents/overview/OverviewSide.tsx — the Overview's right column: Model, Details, Recent sessions.
//
// Model is a read-out with a Change link to the Model tab (choosing happens
// there). Details carry the agent's type, config directory, uid and when it was
// registered — no Title or Name field: an agent's name is fixed to its type
// (spec agent-registry, revise-web-ui-ia). Recent sessions are its three latest
// CLI sessions, hidden when it has none.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { agentSessionPath, agentTabPath } from "@/lib/agents/routes";
import type { AgentOut } from "@/lib/api/agents";
import { useAgentTranscripts } from "@/lib/hooks/useAgentTranscripts";
import { cn, formatDateTime } from "@/lib/utils";

import { formatAgo } from "./age";
import { InfoRow, OverviewSection } from "./OverviewSection";
import { useProviderLabel } from "./useProviderLabel";

const K = "agents.overviewTab";

function SideLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex items-center gap-1 whitespace-nowrap text-xs font-medium text-accent-text hover:underline"
    >
      {children}
      <ChevronRight aria-hidden className="size-3" />
    </Link>
  );
}

function capitalize(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1);
}

export function OverviewModel({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const provider = useProviderLabel(agent.type);
  return (
    <OverviewSection
      title={t(`${K}.model.heading`)}
      aside={<SideLink to={agentTabPath(agent.type, "model")}>{t(`${K}.model.change`)}</SideLink>}
    >
      <dl className="flex flex-col">
        <InfoRow label={t(`${K}.model.provider`)}>
          {provider ?? <Skeleton className="h-4 w-40" />}
        </InfoRow>
        <InfoRow label={t(`${K}.model.model`)} mono={!!agent.model}>
          {agent.model ?? t(`${K}.model.perConversation`)}
        </InfoRow>
        <InfoRow label={t(`${K}.model.${agent.type === "codex" ? "reasoningEffort" : "effort"}`)}>
          {agent.effort ? capitalize(agent.effort) : t(`${K}.model.defaultEffort`)}
        </InfoRow>
      </dl>
    </OverviewSection>
  );
}

export function OverviewDetails({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  return (
    <OverviewSection title={t(`${K}.details.heading`)}>
      <dl className="flex flex-col">
        <InfoRow label={t("agents.type")}>{agentTypeLabel(agent.type)}</InfoRow>
        <InfoRow label={t("agents.configDir")} mono>
          {agent.config_dir}
        </InfoRow>
        <InfoRow label={t(`${K}.details.uid`)} mono>
          {agent.uid}
        </InfoRow>
        <InfoRow label={t(`${K}.details.registered`)}>
          {formatDateTime(agent.created_at).slice(0, 10)}
        </InfoRow>
      </dl>
    </OverviewSection>
  );
}

export function OverviewRecentSessions({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const list = useAgentTranscripts(agent.uid, { limit: 3 });
  const sessions = list.data?.sessions ?? [];
  if (sessions.length === 0) return null;
  return (
    <OverviewSection
      title={t(`${K}.sessions.heading`)}
      aside={
        <SideLink to={agentTabPath(agent.type, "sessions")}>
          {t(`${K}.sessions.all`, { count: list.data?.total ?? sessions.length })}
        </SideLink>
      }
      className="gap-1"
    >
      <ul className="flex flex-col">
        {sessions.slice(0, 3).map((s, i) => {
          const when = s.last_activity_at ?? s.started_at;
          return (
            <li key={s.source_path} className={cn(i > 0 && "border-t border-border-subtle")}>
              <Link
                to={agentSessionPath(agent.type, s.source_path)}
                className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-text hover:bg-surface-hover"
              >
                <span className="flex min-w-0 grow flex-col gap-0.5">
                  <span className="break-words text-sm font-medium">
                    {s.title || t(`${K}.sessions.untitled`)}
                  </span>
                  {s.project_path ? (
                    <span className="break-all text-xs text-text-subtle">
                      {abbreviateHomePath(s.project_path)}
                    </span>
                  ) : null}
                </span>
                {when ? (
                  <span className="shrink-0 text-xs text-text-subtle">{formatAgo(t, when)}</span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </OverviewSection>
  );
}
