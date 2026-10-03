// src/components/agents/detail/AgentDetailHeader.tsx — the agent page's header: mark, name, status pill, New conversation, ⋯.
//
// One fixed header for every state: the agent's mark (faded while it is off),
// its name, one StatusPill, then New conversation and the ⋯ menu on the right.
// An agent whose program is not on this Mac has nothing to converse with, so it
// shows ⋯ only. The header never changes into a fix button: Connect, Repair,
// Turn on and Check again live in the Overview's Connection section. There is
// no meta line; the version is in Overview's Details. Rotate proxy token is in
// ⋯, only while the agent routes through Coffer's proxy.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MessageSquarePlus } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import type { useAgentRowActions } from "@/components/agents/list/useAgentRowActions";
import { AgentPendingStatus } from "@/components/agents/list/AgentPendingStatus";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/status/StatusPill";
import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { agentTypeLabel } from "@/lib/agents/display";
import { hookNotApproved } from "@/lib/agents/hookRows";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";
import { agentRowStateKey, agentRowTone, type AgentRowState } from "@/lib/agents/rowState";
import type { AgentTypeOut } from "@/lib/api/agents";
import { useAgent, useAgentHooks } from "@/lib/hooks/useAgents";
import { cn } from "@/lib/utils";
import { useRotateProxyAction } from "./useRotateProxyToken";

type RowActions = ReturnType<typeof useAgentRowActions>;

interface Props {
  typeRow: AgentTypeOut;
  rowActions: RowActions;
}

/** States with no program to talk to: the header offers ⋯ only. */
const NO_PROGRAM: readonly AgentRowState[] = ["not_installed", "config_left_behind", "not_found"];

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

  // Rotate sits before Disconnect / Turn off, with the other agent-level actions.
  const actions: MenuAction[] = [...rowActions.actions];
  if (rotate) {
    const at = actions.findIndex((a) => ["disconnect", "disable", "enable"].includes(a.key));
    actions.splice(at < 0 ? actions.length : at, 0, rotate);
  }

  return (
    <PageHeader
      title={
        <span className="inline-flex items-center gap-2.5">
          <span className={cn(state === "disabled" && "opacity-[.45]")}>
            <AgentBadge type={typeRow.type} size="lg" tooltip={false} />
          </span>
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
        <div className="flex items-center gap-2">
          {NO_PROGRAM.includes(state) ? null : (
            <Button variant="outline" size="sm" asChild>
              <Link to="/conversations">
                <MessageSquarePlus aria-hidden className="size-3.5" />
                {t("agents.detail.newConversation")}
              </Link>
            </Button>
          )}
          {actions.length > 0 ? (
            <ActionMenu label={t("agents.detail.moreActions", { name })} actions={actions} />
          ) : null}
        </div>
      }
    />
  );
}
