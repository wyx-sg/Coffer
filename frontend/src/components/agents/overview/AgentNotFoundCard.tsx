// src/components/agents/overview/AgentNotFoundCard.tsx — the Overview when an added agent's program and folder are both gone (board 2.1.14).
//
// Coffer's resources don't reach it until it is back, so the tab says what is
// missing and the ways out: reinstall it and check again, point the agent at
// the folder it uses now, or remove it from Coffer (the confirm is the page's).
import { Trans, useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { abbreviateHomePath, agentProgramName, agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";

import type { OverviewActions } from "../AgentOverviewTab";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";

import { FixWay, LastKnownRows, ProblemBanner } from "./FixParts";
import { InlineCode, OverviewSection } from "./OverviewSection";
import { useDetectionCheck } from "./useDetectionCheck";
import { mainConfigPath } from "./paths";

const K = "agents.overviewTab.problem";

interface Props {
  agent: AgentOut;
  actions: OverviewActions;
}

export function AgentNotFoundCard({ agent, actions }: Props) {
  const { t } = useTranslation();
  const { checkedAt } = useDetectionCheck();
  const name = agentTypeLabel(agent.type);
  const dir = abbreviateHomePath(agent.config_dir);

  return (
    <div className="flex flex-col gap-10 lg:flex-row">
      <div className="flex min-w-0 flex-[1.35_1_0] flex-col gap-6">
        <ProblemBanner tone="err" title={t(`${K}.notFound.title`, { name, dir })}>
          <Trans
            i18nKey={`${K}.notFound.body`}
            values={{
              time: checkedAt,
              file: mainConfigPath(agent),
              program: agentProgramName(agent.type),
            }}
            components={{ code: <InlineCode /> }}
          />
        </ProblemBanner>
        <OverviewSection title={t(`${K}.waysToFix`)}>
          <ul className="flex flex-col">
            <FixWay title={t(`${K}.reinstall.title`, { name })} body={t(`${K}.reinstall.body`)}>
              {agent.install_handoff ? (
                <AgentHandoff prompt={agent.install_handoff.prompt} size="sm" />
              ) : null}
            </FixWay>
            <FixWay title={t(`${K}.moved.title`)} body={t(`${K}.moved.body`, { name })}>
              <Button variant="outline" size="sm" onClick={actions.onChangeConfigDir}>
                {t(`${K}.moved.action`)}
              </Button>
            </FixWay>
            <FixWay title={t(`${K}.notUsing.title`, { name })} body={t(`${K}.notUsing.body`)}>
              <Button variant="danger" size="sm" onClick={actions.onRemove}>
                {t(`${K}.notUsing.action`)}
              </Button>
            </FixWay>
          </ul>
        </OverviewSection>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-[22px]">
        <OverviewSection title={t(`${K}.lastKnown`)}>
          <dl className="flex flex-col">
            <LastKnownRows agent={agent} />
          </dl>
        </OverviewSection>
      </div>
    </div>
  );
}
