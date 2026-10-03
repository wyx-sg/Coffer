// src/components/agents/overview/ConfigLeftBehindCard.tsx — the Overview when the agent's program is gone but its folder stays (board 2.1.13).
//
// Coffer can't connect an agent that isn't installed and leaves the folder as
// it is. Two sections, no banner: "Install {name}" (one line, Check again and
// the hand-off to an agent) and "Left in {dir}" (what Coffer last knew: the
// version, the files, the model and provider, when it was last seen).
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { AskAgentButton } from "@/components/handoff/AskAgentButton";
import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath, agentProgramName, agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut, AgentTypeOut } from "@/lib/api/agents";
import { useAgentConfigFiles } from "@/lib/hooks/useAgents";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";
import { formatMoment } from "@/lib/time";
import { cn } from "@/lib/utils";

import type { OverviewActions } from "../AgentOverviewTab";
import { InfoRow, SectionLine } from "./OverviewParts";
import { baseName } from "./paths";
import { useDetectionCheck } from "./useDetectionCheck";
import { useProviderLabel } from "./useProviderLabel";

const K = "agents.overviewTab.problem";

interface Props {
  agent: AgentOut;
  typeRow: AgentTypeOut;
  actions: OverviewActions;
}

export function ConfigLeftBehindCard({ agent, typeRow }: Props) {
  const { t, i18n } = useTranslation();
  const { checking, check } = useDetectionCheck();
  const configFiles = useAgentConfigFiles(agent.uid);
  const models = useFeatureEnabled("models") === true;
  const provider = useProviderLabel(agent);
  const files = (configFiles.data ?? []).filter((f) => f.exists).map((f) => baseName(f.path));
  const name = agentTypeLabel(agent.type);
  const dir = abbreviateHomePath(agent.config_dir);
  const version = typeRow.version ?? agent.version;

  return (
    <div className="flex max-w-[920px] flex-col gap-8">
      <Section
        title={t(`${K}.install.title`, { name })}
        as="h2"
        help={<p className="text-xs">{t(`${K}.install.help`)}</p>}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={check} disabled={checking}>
              <RefreshCw aria-hidden className={cn(checking && "animate-spin")} />
              {t(`${K}.checkAgain`)}
            </Button>
            {agent.install_handoff ? (
              <AskAgentButton prompt={agent.install_handoff.prompt} />
            ) : null}
          </>
        }
      >
        <SectionLine>
          {t(`${K}.leftBehind.line`, { dir, program: agentProgramName(agent.type) })}
        </SectionLine>
      </Section>
      <Section title={t(`${K}.leftIn`, { dir })} as="h2">
        <dl className="flex flex-col">
          <InfoRow label={t(`${K}.lastVersion`)} mono={!!version}>
            {version ? `v${version.replace(/^v/, "")}` : t("common.emptyValue")}
          </InfoRow>
          <InfoRow label={t(`${K}.files`)} mono={files.length > 0}>
            {files.length > 0 ? files.join(", ") : t("common.emptyValue")}
          </InfoRow>
          <InfoRow label={t("agents.overviewTab.model.model")} mono={!!agent.model}>
            {agent.model ?? t("common.emptyValue")}
          </InfoRow>
          {models ? (
            <InfoRow label={t("agents.overviewTab.model.provider")}>
              {provider ?? t("common.emptyValue")}
            </InfoRow>
          ) : null}
          <InfoRow label={t(`${K}.lastSeen`)}>
            {formatMoment(agent.updated_at, i18n.language, t)}
          </InfoRow>
        </dl>
      </Section>
    </div>
  );
}
