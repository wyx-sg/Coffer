// frontend/src/components/agents/AgentOverviewTab.tsx — the agent detail page's
// Overview tab: a compact type + config-dir summary. Split out of
// AgentDetailPage so the page stays within the file-size limit.
import { useTranslation } from "react-i18next";

import { Card, CardContent } from "@/components/ui/card";
import type { AgentOut } from "@/lib/api/agents";

export function AgentOverviewTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardContent className="py-6">
        <dl className="grid grid-cols-[10rem_1fr] gap-y-3 text-sm">
          <dt className="text-muted-foreground">{t("agents.type")}</dt>
          <dd>{agent.type}</dd>
          <dt className="text-muted-foreground">{t("agents.configDir")}</dt>
          <dd className="font-mono text-xs">{agent.config_dir}</dd>
        </dl>
      </CardContent>
    </Card>
  );
}
