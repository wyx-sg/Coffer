// src/components/agents/detail/AgentDetailHeader.tsx — the agent page's header: mark, name, status pill, ⋯.
//
// One fixed header for every state: the agent's mark ),
// its name, one StatusPill, then the ⋯ menu on the right. The header never changes into a fix button: Connect, Repair,
// and Check again live in the Overview's Connection section. There is
// no meta line; the version is in Overview's Details. Rotate proxy token is in
// ⋯, only while the agent routes through Coffer's proxy.
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import type { useAgentRowActions } from "@/components/agents/list/useAgentRowActions";
import { AgentPendingStatus } from "@/components/agents/list/AgentPendingStatus";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/status/StatusPill";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { agentTypeLabel } from "@/lib/agents/display";
import { hookNotApproved } from "@/lib/agents/hookRows";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";
import { agentRowStateKey, agentRowTone } from "@/lib/agents/rowState";
import type { AgentTypeOut } from "@/lib/api/agents";
import { useAgent, useAgentHooks } from "@/lib/hooks/useAgents";
import { useRotateProxyAction } from "./useRotateProxyToken";

type RowActions = ReturnType<typeof useAgentRowActions>;

interface Props {
  typeRow: AgentTypeOut;
  rowActions: RowActions;
}

export function AgentDetailHeader({ typeRow, rowActions }: Props) {
  const { t } = useTranslation();
  const name = agentTypeLabel(typeRow.type);
  const state = rowActions.state;
  const uid = typeRow.uid ?? "";
  const hooks = useAgentHooks(uid);
  const agent = useAgent(uid).data;
  const rotate = useRotateProxyAction(agent);
  // A connected Codex whose hook is not approved (or changed since it was) reads Hook not approved.
  const memoryOn = useFeatureEnabled("memory") === true;
  const notApproved = memoryOn && state === "connected" && hookNotApproved(hooks.data?.coffer_hook);

  // Rotate sits before Disconnect, with the other agent-level actions.
  const actions: MenuAction[] = [...rowActions.actions];
  if (rotate) {
    const at = actions.findIndex((a) => a.key === "disconnect");
    actions.splice(at < 0 ? actions.length : at, 0, rotate);
  }

  return (
    <PageHeader
      title={
        <span className="inline-flex items-center gap-2.5">
          <AgentBadge type={typeRow.type} size="lg" tooltip={false} />
          {name}
        </span>
      }
      badges={
        rowActions.pending ? (
          <AgentPendingStatus pending={rowActions.pending} />
        ) : (
          <StatusPill tone={notApproved ? "warn" : agentRowTone(state)}>
            {t(notApproved ? "agents.stateHeader.hook_untrusted" : agentRowStateKey(state))}
          </StatusPill>
        )
      }
      actions={
        actions.length > 0 ? (
          <ActionMenu label={t("agents.detail.moreActions", { name })} actions={actions} />
        ) : null
      }
    />
  );
}
