// frontend/src/components/agents/AgentBulkActions.tsx
// Bulk action buttons rendered in the agents-table selection bar: install the
// Coffer MCP into every selected agent at once, or open a skill-picker dialog to
// bind a set of Coffer-managed skills to all of them. Kept out of AgentTable.tsx
// so that file stays within its size budget.
//
// Install/uninstall fan out per-agent with Promise.allSettled (via useBulkMutate)
// so one failing agent never aborts the rest; a single summary toast reports the
// outcome and one invalidation burst refreshes the list + per-agent status.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plug, Sparkles, Unplug } from "lucide-react";

import { AgentInstallSkillsDialog } from "@/components/agents/AgentInstallSkillsDialog";
import { Button } from "@/components/ui/button";
import { agentsApi, type AgentOut } from "@/lib/api/agents";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

export function AgentBulkActions({ agents, onDone }: { agents: AgentOut[]; onDone: () => void }) {
  const { t } = useTranslation();
  const [skillsOpen, setSkillsOpen] = useState(false);

  const bulk = useBulkMutate({
    invalidate: [["agents"], ...agents.map((a) => ["agents", a.name, "mcp-install"] as const)],
  });

  const run = async (op: (name: string) => Promise<unknown>) => {
    await bulk.run(agents, (a) => op(a.name));
    onDone();
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        disabled={bulk.isPending}
        onClick={() => void run(agentsApi.mcpInstall)}
      >
        <Plug className="mr-1.5 size-3.5" /> {t("agents.bulkInstallMcp")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={bulk.isPending}
        onClick={() => void run(agentsApi.mcpUninstall)}
      >
        <Unplug className="mr-1.5 size-3.5" /> {t("agents.mcp.uninstall")}
      </Button>
      <Button size="sm" variant="outline" onClick={() => setSkillsOpen(true)}>
        <Sparkles className="mr-1.5 size-3.5" /> {t("agents.bulkInstallSkills")}
      </Button>

      <AgentInstallSkillsDialog
        agents={agents}
        open={skillsOpen}
        onOpenChange={setSkillsOpen}
        onInstalled={onDone}
      />
    </>
  );
}
