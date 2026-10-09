// src/components/agents/detail/AgentDetailHeader.tsx — the agent page's header: mark, name, status pill, ⋯.
//
// One fixed header for every state: the agent's mark ),
// its name, one StatusPill, then the ⋯ menu on the right. The header never changes into a fix button: Connect and
// Repair live in the Overview's Connection section. There is
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
import { agentRowStateKey, agentRowTone } from "@/lib/agents/rowState";
import type { AgentTypeOut } from "@/lib/api/agents";
import { useAgent } from "@/lib/hooks/useAgents";
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
  const agent = useAgent(uid).data;
  const rotate = useRotateProxyAction(agent);

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
          <StatusPill tone={agentRowTone(state)}>{t(agentRowStateKey(state))}</StatusPill>
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
