// src/components/agents/detail/AgentDetailHeader.tsx — the agent page's header: mark, name, Coffer state, the one action, the ⋯ menu.
//
// Spec agent-registry "Show the Coffer connection on the agent pages": the
// header offers the action the state calls for — Connect to Coffer when not
// connected, Repair (naming the memory hook when only it is off) when the
// connection is partial, Check again while Codex has not approved Coffer's
// hook, Enable when switched off, Add when not added — and a connected
// agent's own next step, a new conversation (Disconnect is the Overview's
// button, and previews what it removes). The ⋯ menu holds what has no button. No title or rename:
// an agent is named by its type; its version and config directory are in the
// Overview's Details.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  MessageSquarePlus,
  Plug,
  Plus,
  Power,
  RefreshCw,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import { AgentBadge, type AgentBadgeState } from "@/components/agent/AgentBadge";
import type { useAgentRowActions } from "@/components/agents/list/useAgentRowActions";
import { AgentPendingStatus } from "@/components/agents/list/AgentPendingStatus";
import { PageHeader } from "@/components/PageHeader";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import { agentTypeLabel } from "@/lib/agents/display";
import { hookAwaitsApproval, repairsOnlyHook } from "@/components/agents/overview/connectionCopy";
import { agentRowStateKey, agentRowTone, type AgentRowState } from "@/lib/agents/rowState";
import type { AgentTypeOut } from "@/lib/api/agents";
import { useAgentConnection, useAgentHooks } from "@/lib/hooks/useAgents";
import { cn } from "@/lib/utils";

type RowActions = ReturnType<typeof useAgentRowActions>;

interface Props {
  typeRow: AgentTypeOut;
  rowActions: RowActions;
}

/** How the agent's mark reads for its state (Foundations-AgentBadge). */
function badgeState(state: AgentRowState): AgentBadgeState {
  if (state === "connected") return "connected";
  if (state === "disabled") return "disabled";
  if (state === "not_installed" || state === "config_left_behind" || state === "not_found")
    return "not-installed";
  return "not-connected";
}

/**
 * The header's word for a state; a connected agent says what it is connected
 * to, or — when Codex has not approved Coffer's hook — that the hook waits for
 * approval. An agent whose program is gone reads Not installed.
 */
function stateWordKey(state: AgentRowState, awaitingApproval: boolean): string {
  if (awaitingApproval) return "agents.stateHeader.hook_untrusted";
  if (state === "connected") return "agents.stateHeader.connected";
  if (state === "config_left_behind") return "agents.state.not_installed";
  return agentRowStateKey(state);
}

interface HeaderAction {
  label: string;
  icon: LucideIcon;
  run?: () => void;
  to?: string;
  pending?: boolean;
}

interface HeaderContext {
  /** Codex has not approved Coffer's (otherwise current) hook. */
  awaitingApproval: boolean;
  /** Only the memory hook is off, so the repair names it. */
  hookOnly: boolean;
  checkAgain: () => void;
  checking: boolean;
}

function useHeaderAction(
  state: AgentRowState,
  open: RowActions["open"],
  ctx: HeaderContext,
): HeaderAction | null {
  const { t } = useTranslation();
  if (ctx.awaitingApproval) {
    return {
      label: t("agents.detail.checkAgain"),
      icon: RefreshCw,
      run: ctx.checkAgain,
      pending: ctx.checking,
    };
  }
  switch (state) {
    case "connected":
      return {
        label: t("agents.detail.newConversation"),
        icon: MessageSquarePlus,
        to: "/conversations",
      };
    case "not_connected":
      return { label: t("agents.detail.connect"), icon: Plug, run: () => open.change("connect") };
    // A partial connection reads Needs repair and offers the repair, which puts
    // the missing parts back; when only the memory hook is off it names it.
    case "needs_repair":
      return {
        label: t(ctx.hookOnly ? "agents.detail.repairHook" : "agents.detail.repair"),
        icon: Wrench,
        run: () => open.change("connect"),
      };
    case "disabled":
      return { label: t("agents.detail.enable"), icon: Power, run: open.enable };
    case "not_added":
    case "never_run":
      return { label: t("agents.detail.add"), icon: Plus, run: () => open.change("add") };
    default:
      return null;
  }
}

export function AgentDetailHeader({ typeRow, rowActions }: Props) {
  const { t } = useTranslation();
  const name = agentTypeLabel(typeRow.type);
  const state = rowActions.state;
  const uid = typeRow.uid ?? "";
  const hooks = useAgentHooks(uid);
  const parts = useAgentConnection(uid).data?.parts;
  const awaitingApproval = hookAwaitsApproval(state, hooks.data?.coffer_hook);
  const action = useHeaderAction(state, rowActions.open, {
    awaitingApproval,
    hookOnly: repairsOnlyHook(parts),
    checkAgain: () => void hooks.refetch(),
    checking: hooks.isFetching,
  });
  const busy = !!rowActions.pending;

  return (
    <PageHeader
      back={{ to: "/agents", label: t("agents.title") }}
      title={
        <span className="inline-flex items-center gap-2.5">
          <AgentBadge type={typeRow.type} size="lg" state={badgeState(state)} tooltip={false} />
          {name}
        </span>
      }
      badges={
        rowActions.pending ? (
          <AgentPendingStatus pending={rowActions.pending} />
        ) : (
          <StatusWord tone={awaitingApproval ? "warn" : agentRowTone(state)}>
            {t(stateWordKey(state, awaitingApproval))}
          </StatusWord>
        )
      }
      actions={
        <div className="flex items-center gap-2">
          {action?.to ? (
            <Button variant="outline" size="sm" asChild>
              <Link to={action.to}>
                <action.icon aria-hidden className="size-3.5" />
                {action.label}
              </Link>
            </Button>
          ) : action ? (
            <Button
              size="sm"
              variant={action.pending === undefined ? "default" : "outline"}
              onClick={action.run}
              disabled={action.pending || busy}
              loading={busy}
            >
              <action.icon
                aria-hidden
                className={cn("size-3.5", action.pending && "animate-spin")}
              />
              {action.label}
            </Button>
          ) : null}
          {rowActions.actions.length > 0 ? (
            <ActionMenu
              label={t("agents.detail.moreActions", { name })}
              actions={rowActions.actions}
            />
          ) : null}
        </div>
      }
    />
  );
}
