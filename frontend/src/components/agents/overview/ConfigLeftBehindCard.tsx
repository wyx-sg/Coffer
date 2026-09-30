// src/components/agents/overview/ConfigLeftBehindCard.tsx — the Overview when the agent's program is gone but its folder stays (board 2.1.13).
//
// Coffer can't connect an agent that isn't installed and leaves the folder as
// it is, so the tab says what it found (the directory and the files still in
// it, no program on PATH) and the one way out: install it and check again.
// Revealing the folder or taking the agent off the list stay in the ⋯ menu.
import { Trans, useTranslation } from "react-i18next";

import {
  abbreviateHomePath,
  agentInstallCommand,
  agentProgramName,
  agentTypeLabel,
} from "@/lib/agents/display";
import type { AgentOut, AgentTypeOut } from "@/lib/api/agents";
import { useAgentConfigFiles } from "@/lib/hooks/useAgents";

import type { OverviewActions } from "../AgentOverviewTab";
import { FixWay, InstallCommand, LastKnownRows, ProblemBanner } from "./FixParts";
import { useDetectionCheck } from "./useDetectionCheck";
import { InfoRow, InlineCode, OverviewSection } from "./OverviewSection";
import { baseName } from "./paths";

const K = "agents.overviewTab.problem";

interface Props {
  agent: AgentOut;
  typeRow: AgentTypeOut;
  actions: OverviewActions;
}

export function ConfigLeftBehindCard({ agent, typeRow }: Props) {
  const { t } = useTranslation();
  const { checkedAt } = useDetectionCheck();
  const configFiles = useAgentConfigFiles(agent.uid);
  const files = (configFiles.data ?? []).filter((f) => f.exists).map((f) => baseName(f.path));
  const name = agentTypeLabel(agent.type);
  const dir = abbreviateHomePath(agent.config_dir);
  const version = typeRow.version ?? agent.version;

  return (
    <div className="flex flex-col gap-10 lg:flex-row">
      <div className="flex min-w-0 flex-[1.35_1_0] flex-col gap-6">
        <ProblemBanner tone="warn" title={t(`${K}.leftBehind.title`, { name })}>
          <Trans
            i18nKey={`${K}.leftBehind.${files.length > 0 ? "body" : "bodyNoFiles"}`}
            values={{
              time: checkedAt,
              dir,
              files: files.join(", "),
              program: agentProgramName(agent.type),
            }}
            components={{ code: <InlineCode /> }}
          />
        </ProblemBanner>
        <OverviewSection title={t(`${K}.waysToFix`)}>
          <ul className="flex flex-col">
            <FixWay title={t(`${K}.install.title`, { name })} body={t(`${K}.install.body`)}>
              <InstallCommand command={agentInstallCommand(agent.type)} />
            </FixWay>
          </ul>
        </OverviewSection>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-[22px]">
        <OverviewSection title={t(`${K}.leftIn`, { dir })}>
          <dl className="flex flex-col">
            <InfoRow label={t(`${K}.files`)} mono={files.length > 0}>
              {files.length > 0 ? files.join(", ") : t("common.emptyValue")}
            </InfoRow>
            <InfoRow label={t(`${K}.lastVersion`)} mono={!!version}>
              {version ?? t("common.emptyValue")}
            </InfoRow>
            <LastKnownRows agent={agent} />
          </dl>
        </OverviewSection>
      </div>
    </div>
  );
}
