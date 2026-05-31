// frontend/src/components/agents/AgentSkillsBulkActions.tsx
// Bulk enable/disable bar for the agent Skills tab's DataTable. Each action fans
// out one per-(skill, agent) enable/disable call over the selected rows with
// Promise.allSettled (via useBulkMutate) so one failure never aborts the rest;
// a single summary toast reports the outcome and the selection clears via
// onDone(). Lives in its own file (and needs `agentName`) to keep
// AgentSkillsTab.tsx under the file-size cap.
import { useTranslation } from "react-i18next";
import { Power, PowerOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { skillsApi, type SkillBindingOut, type SkillOut } from "@/lib/api/skills";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

export interface AgentSkillRow {
  skill: SkillOut;
  binding: SkillBindingOut;
}

export function AgentSkillsBulkActions({
  agentName,
  rows,
  onDone,
}: {
  agentName: string;
  rows: AgentSkillRow[];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const bulk = useBulkMutate({ invalidate: [["skills"]] });

  const runAll = async (op: "enable" | "disable") => {
    await bulk.run(rows, (r) => skillsApi[op](r.skill.name, { agent_name: agentName }));
    onDone();
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        disabled={bulk.isPending}
        onClick={() => void runAll("enable")}
      >
        <Power className="mr-1.5 size-3.5" />
        {t("common.bulk.enable")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={bulk.isPending}
        onClick={() => void runAll("disable")}
      >
        <PowerOff className="mr-1.5 size-3.5" />
        {t("common.bulk.disable")}
      </Button>
    </>
  );
}
