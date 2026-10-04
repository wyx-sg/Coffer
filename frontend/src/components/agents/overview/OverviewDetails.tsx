// src/components/agents/overview/OverviewDetails.tsx — the Overview's Details section: Version, Config directory, UID, Registered.
//
// No Title, Name or Type row: an agent's name is fixed to its type (spec
// agent-registry). The version is the first row since the header no longer
// carries a meta line.
import { useTranslation } from "react-i18next";

import { Section } from "@/components/Section";
import type { AgentOut } from "@/lib/api/agents";
import { formatDay } from "@/lib/time";

import { InfoRow } from "./OverviewParts";

const K = "agents.overviewTab.details";

export function OverviewDetails({ agent, version }: { agent: AgentOut; version: string | null }) {
  const { t, i18n } = useTranslation();
  return (
    <Section title={t(`${K}.heading`)} as="h2">
      <dl className="flex flex-col">
        <InfoRow label={t(`${K}.version`)} mono={!!version}>
          {version ? `v${version.replace(/^v/, "")}` : t("common.emptyValue")}
        </InfoRow>
        <InfoRow label={t("agents.configDir")} mono>
          {agent.config_dir}
        </InfoRow>
        <InfoRow label={t(`${K}.uid`)} mono>
          {agent.uid}
        </InfoRow>
        <InfoRow label={t(`${K}.registered`)}>
          {formatDay(new Date(agent.created_at), i18n.language)}
        </InfoRow>
      </dl>
    </Section>
  );
}
