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
import { useAgentDefaultModel, useAgentModels } from "@/lib/hooks/useAgentModels";
import { useAgentTranscripts } from "@/lib/hooks/useAgentTranscripts";
import { cn, formatDateTime } from "@/lib/utils";

import { formatAgo } from "./age";
import { Section } from "@/components/Section";
import { InfoRow } from "./OverviewParts";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";
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
  // The Provider line and the link to the Model tab belong to the Models
  // feature; with it off they are not shown.
  const models = useFeatureEnabled("models") === true;
  const provider = useProviderLabel(agent);
  // What the agent runs when a conversation picks nothing: the model Coffer set
  // on it; on its own login, the model its own config names. Neither → it
  // chooses for itself, which is said in words, not guessed from a list.
  const onConnection = !!agent.connection_uid;
  const nativeModel = useAgentDefaultModel(onConnection ? "" : agent.type).data ?? null;
  const model = agent.model ?? nativeModel;
  const catalogue = useAgentModels(agent.type).data;
  const effort =
    agent.effort ?? (model ? catalogue?.find((m) => m.id === model)?.default_effort : null) ?? null;
  return (
    <Section
      title={t(`${K}.model.heading`)}
      actions={
        models ? (
          <SideLink to={agentTabPath(agent.type, "model")}>{t(`${K}.model.change`)}</SideLink>
        ) : undefined
      }
    >
      <dl className="flex flex-col">
        {models ? (
          <InfoRow label={t(`${K}.model.provider`)}>
            {provider ?? <Skeleton className="h-4 w-40" />}
          </InfoRow>
        ) : null}
        <InfoRow label={t(`${K}.model.model`)} mono={!!model}>
          {model ?? t(`${K}.model.auto`)}
        </InfoRow>
        <InfoRow label={t(`${K}.model.effort`)}>
          {effort ? capitalize(effort) : t(`${K}.model.auto`)}
        </InfoRow>
      </dl>
    </Section>
  );
}

export function OverviewDetails({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  return (
    <Section title={t(`${K}.details.heading`)}>
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
    </Section>
  );
}

export function OverviewRecentSessions({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const list = useAgentTranscripts(agent.uid, { limit: 3 });
  const sessions = list.data?.sessions ?? [];
  if (sessions.length === 0) return null;
  return (
    <Section
      title={t(`${K}.sessions.heading`)}
      actions={
        <SideLink to={agentTabPath(agent.type, "sessions")}>{t(`${K}.sessions.all`)}</SideLink>
      }
      gap="tight"
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
    </Section>
  );
}
