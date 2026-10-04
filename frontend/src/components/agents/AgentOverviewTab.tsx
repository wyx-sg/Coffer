// src/components/agents/AgentOverviewTab.tsx — the agent detail page's Overview tab (boards 2.1.08–2.1.14).
//
// One column, 920 wide: Connection (its one fix at the title's right) → What
// this agent can use (six tiles) → Model (with Change…) → Details. Detection
// wins: an agent whose program is gone replaces the tab with the config-left-
// behind or not-found sections. Every write goes through `actions`, which the
// page wires to its dialogs.
import type { AgentOut, AgentTypeOut } from "@/lib/api/agents";
import { agentRowState } from "@/lib/agents/rowState";
import { useAgentConnection, useAgentHooks } from "@/lib/hooks/useAgents";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";
import { useResource } from "@/lib/hooks/useResources";

import { OverviewModelSection } from "./model/OverviewModelSection";
import { AgentNotFoundCard } from "./overview/AgentNotFoundCard";
import { ConfigLeftBehindCard } from "./overview/ConfigLeftBehindCard";
import { OverviewConnection } from "./overview/OverviewConnection";
import { OverviewDetails } from "./overview/OverviewDetails";
import { OverviewSummary } from "./overview/OverviewSummary";

export interface OverviewActions {
  /** Open the connection-change preview: connect (also Repair) or disconnect. */
  onConnection: (kind: "connect" | "disconnect") => void;
  onEnable: () => void;
  /** "Use a different config directory…" */
  onChangeConfigDir: () => void;
  /** Connect / disconnect / enable is running on the agent: its buttons wait. */
  busy?: boolean;
}

interface Props {
  agent: AgentOut;
  typeRow: AgentTypeOut;
  actions: OverviewActions;
}

export function AgentOverviewTab({ agent, typeRow, actions }: Props) {
  if (typeRow.state === "config_only") {
    return <ConfigLeftBehindCard agent={agent} typeRow={typeRow} actions={actions} />;
  }
  if (typeRow.state === "missing") return <AgentNotFoundCard agent={agent} actions={actions} />;
  return <OverviewBody agent={agent} typeRow={typeRow} actions={actions} />;
}

function OverviewBody({ agent, typeRow, actions }: Props) {
  const connection = useAgentConnection(agent.uid);
  const hooks = useAgentHooks(agent.uid);
  const memoryOn = useFeatureEnabled("memory") === true;
  const resource = useResource(agent.uid);
  const enabled = resource.data?.enabled ?? true;
  const state = agentRowState(
    { state: typeRow.state, uid: agent.uid },
    connection.data?.state,
    enabled,
  );

  return (
    <div className="flex max-w-[920px] flex-col gap-8">
      <OverviewConnection
        agent={agent}
        typeRow={typeRow}
        state={state}
        connection={connection.data}
        hook={memoryOn ? hooks.data?.coffer_hook : undefined}
        failed={connection.isError}
        actions={actions}
        onCheckHook={() => void hooks.refetch()}
        checking={hooks.isFetching}
      />
      <OverviewSummary
        agent={agent}
        typeRow={typeRow}
        disabled={!enabled}
        notConnected={state === "not_connected"}
      />
      <OverviewModelSection agent={agent} />
      <OverviewDetails agent={agent} version={typeRow.version ?? agent.version ?? null} />
    </div>
  );
}
