// frontend/src/components/agents/AgentBulkActions.tsx
// Bulk action buttons rendered in the agents-table selection bar: install or
// uninstall the Coffer MCP across every selected agent at once. Kept out of
// AgentTable.tsx so that file stays within its size budget.
//
// Install/uninstall fan out per-agent with Promise.allSettled (via useBulkMutate)
// so one failing agent never aborts the rest; a single summary toast reports the
// outcome and one invalidation burst refreshes the list + per-agent status.
import { useTranslation } from "react-i18next";
import { Plug, Unplug } from "lucide-react";

import { TableActionButton } from "@/components/table/TableActionButton";
import { agentsApi, type AgentOut } from "@/lib/api/agents";
import { agentMcpInstallKey, agentsKey } from "@/lib/api/queryKeys";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

export function AgentBulkActions({ agents, onDone }: { agents: AgentOut[]; onDone: () => void }) {
  const { t } = useTranslation();

  const bulk = useBulkMutate({
    invalidate: [agentsKey, ...agents.map((a) => agentMcpInstallKey(a.uid))],
  });

  const run = async (op: (uid: string) => Promise<unknown>) => {
    await bulk.run(agents, (a) => op(a.uid));
    onDone();
  };

  return (
    <>
      <TableActionButton
        icon={Plug}
        label={t("agents.bulkInstallMcp")}
        disabled={bulk.isPending}
        onClick={() => void run(agentsApi.mcpInstall)}
      />
      <TableActionButton
        icon={Unplug}
        label={t("agents.mcp.uninstall")}
        disabled={bulk.isPending}
        onClick={() => void run(agentsApi.mcpUninstall)}
      />
    </>
  );
}
