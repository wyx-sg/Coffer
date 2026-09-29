// frontend/src/components/agents/AgentBulkActions.tsx
// Bulk action buttons rendered in the agents-table selection bar: connect every
// selected agent to Coffer, or disconnect them, at once (spec agent-registry
// "Show the Coffer connection on the agent pages"). Kept out of
// AgentTable.tsx so that file stays within its size budget.
//
// Connect/disconnect fan out per-agent with Promise.allSettled (via useBulkMutate)
// so one failing agent never aborts the rest; a single summary toast reports the
// outcome and one invalidation burst refreshes the list + per-agent status.
import { useTranslation } from "react-i18next";
import { Plug, Unplug } from "lucide-react";

import { TableActionButton } from "@/components/table/TableActionButton";
import { agentsApi, type AgentOut } from "@/lib/api/agents";
import { agentConnectionKey, agentsKey } from "@/lib/api/queryKeys";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

export function AgentBulkActions({ agents, onDone }: { agents: AgentOut[]; onDone: () => void }) {
  const { t } = useTranslation();

  const bulk = useBulkMutate({
    invalidate: [agentsKey, ...agents.map((a) => agentConnectionKey(a.uid))],
  });

  const run = async (op: (uid: string) => Promise<unknown>) => {
    await bulk.run(agents, (a) => op(a.uid));
    onDone();
  };

  return (
    <>
      <TableActionButton
        icon={Plug}
        label={t("agents.cofferConnection.connect")}
        disabled={bulk.isPending}
        onClick={() => void run(agentsApi.connect)}
      />
      <TableActionButton
        icon={Unplug}
        label={t("agents.cofferConnection.disconnect")}
        disabled={bulk.isPending}
        onClick={() => void run(agentsApi.disconnect)}
      />
    </>
  );
}
