// src/components/agents/AgentOverviewTab.tsx — the agent detail page's Overview tab (boards 2.1.08–2.1.14).
//
// Two columns. Left: the Coffer connection (state, one sentence, its one
// action, one row per part) and "What this agent can use" — a summary row per
// kind opening its tab. Right: the model read-out (chosen on the Model tab), the
// agent's details (no Title or Name field — spec agent-registry, revise-web-ui-ia)
// and its recent sessions. Detection wins: an agent whose program is gone
// replaces the whole tab with the config-left-behind or not-found fix card.
// Every write goes through `actions`, which the page wires to its dialogs.
import type { AgentOut, AgentTypeOut } from "@/lib/api/agents";
import { agentRowState } from "@/lib/agents/rowState";
import { useAgentConnection, useAgentHooks } from "@/lib/hooks/useAgents";
import { useResource } from "@/lib/hooks/useResources";

import { AgentNotFoundCard } from "./overview/AgentNotFoundCard";
import { ConfigLeftBehindCard } from "./overview/ConfigLeftBehindCard";
import { OverviewConnection } from "./overview/OverviewConnection";
import { OverviewDetails, OverviewModel, OverviewRecentSessions } from "./overview/OverviewSide";
import { OverviewSummary } from "./overview/OverviewSummary";

export interface OverviewActions {
  /** Open the connection-change preview: connect (also Repair) or disconnect. */
  onConnection: (kind: "connect" | "disconnect") => void;
  onEnable: () => void;
  /** "Change config directory" / "Use a different config directory…" */
  onChangeConfigDir: () => void;
  /** "Remove from Coffer" / "Remove from list" (the confirm dialog is the integrator's). */
  onRemove: () => void;
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
  const resource = useResource(agent.uid);
  const enabled = resource.data?.enabled ?? true;
  const state = agentRowState(
    { state: typeRow.state, uid: agent.uid },
    connection.data?.state,
    enabled,
  );

  return (
    <div className="flex flex-col gap-10 lg:flex-row">
      <div className="flex min-w-0 flex-[1.35_1_0] flex-col gap-6">
        <OverviewConnection
          agent={agent}
          typeRow={typeRow}
          state={state}
          connection={connection.data}
          hook={hooks.data?.coffer_hook}
          failed={connection.isError}
          actions={actions}
        />
        <OverviewSummary agent={agent} typeRow={typeRow} disabled={!enabled} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-[22px]">
        <OverviewModel agent={agent} />
        <OverviewDetails agent={agent} />
        <OverviewRecentSessions agent={agent} />
      </div>
    </div>
  );
}
