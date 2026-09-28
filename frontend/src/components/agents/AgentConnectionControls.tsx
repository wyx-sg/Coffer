// frontend/src/components/agents/AgentConnectionControls.tsx — spec
// agent-registry "Show the Coffer connection on the agent pages".
//
// An agent's Coffer connection is every part Coffer writes into the agent's own
// config that applies now: the gateway MCP entry always, the memory delivery
// hook while Memory is switched on. The header control connects (installs
// every part) or disconnects (behind a confirm — it cuts the agent off from the
// gateway); a partly installed connection reads "Needs repair" and offers
// Connect, which puts the missing parts back. Which parts exist lives behind the
// help tooltip, not inline. The badge is the Agents table's at-a-glance column.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, CircleHelp, Plug, Unplug, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { CofferConnection } from "@/lib/api/agents";
import { useAgentConnection, useAgentConnect } from "@/lib/hooks/useAgents";

const PART_KEYS = ["mcp", "memory_hook"] as const;

function stateLabel(state: CofferConnection["state"]): string {
  if (state === "connected") return "agents.cofferConnection.connected";
  if (state === "partial") return "agents.cofferConnection.needsRepair";
  return "agents.cofferConnection.notConnected";
}

/** The "?" beside the action: which parts a connection installs, and — when
 *  the status is known — which of them are in place. */
function ConnectionHelp({ connection }: { connection: CofferConnection | undefined }) {
  const { t } = useTranslation();
  const installed = new Map(connection?.parts.map((p) => [p.key, p.installed]));
  const memoryOff = connection !== undefined && !installed.has("memory_hook");
  // Its own provider, like the other self-contained tooltips here, so the
  // control renders wherever it is mounted.
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex size-6 items-center justify-center rounded-md text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={t("agents.cofferConnection.helpLabel")}
          >
            <CircleHelp className="size-4" aria-hidden />
          </button>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs space-y-1.5">
          <p>{t("agents.cofferConnection.helpIntro")}</p>
          <ul className="space-y-1">
            {PART_KEYS.map((key) => {
              const state = installed.get(key);
              return (
                <li key={key} className="flex items-start gap-1.5">
                  {state === true ? (
                    <Check className="mt-0.5 size-3 shrink-0 text-status-ok" aria-hidden />
                  ) : state === false ? (
                    <X className="mt-0.5 size-3 shrink-0 text-destructive" aria-hidden />
                  ) : (
                    <span className="mt-0.5 size-3 shrink-0" aria-hidden />
                  )}
                  <span>{t(`agents.cofferConnection.parts.${key}`)}</span>
                </li>
              );
            })}
          </ul>
          {memoryOff ? (
            <p className="text-muted-foreground">{t("agents.cofferConnection.memoryOff")}</p>
          ) : null}
          {connection?.state === "partial" ? (
            <p>{t("agents.cofferConnection.repairHint")}</p>
          ) : null}
          <p className="text-muted-foreground">{t("agents.cofferConnection.disconnectNote")}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function AgentConnectionButton({ uid }: { uid: string }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const status = useAgentConnection(uid);
  const mutate = useAgentConnect(uid);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const state = status.data?.state;

  const run = (connect: boolean) =>
    mutate.mutate(connect, {
      onSuccess: () => {
        setConfirmOpen(false);
        toast.success(
          t(
            connect
              ? "agents.cofferConnection.connectedToast"
              : "agents.cofferConnection.disconnectedToast",
          ),
        );
      },
    });

  return (
    <div className="flex items-center gap-1.5">
      {state === "partial" ? (
        <Badge variant="outline" className="text-status-warn">
          {t("agents.cofferConnection.needsRepair")}
        </Badge>
      ) : null}
      {state === "connected" ? (
        <Button
          variant="outline"
          size="sm"
          disabled={mutate.isPending}
          onClick={() => setConfirmOpen(true)}
        >
          <Unplug className="mr-1.5 size-3.5" />
          {mutate.isPending ? t("common.saving") : t("agents.cofferConnection.disconnect")}
        </Button>
      ) : (
        <Button size="sm" disabled={mutate.isPending || status.isPending} onClick={() => run(true)}>
          <Plug className="mr-1.5 size-3.5" />
          {mutate.isPending ? t("common.saving") : t("agents.cofferConnection.connect")}
        </Button>
      )}
      <ConnectionHelp connection={status.data} />
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t("agents.cofferConnection.disconnectConfirm.title")}
        description={t("agents.cofferConnection.disconnectConfirm.body")}
        confirmLabel={
          mutate.isPending ? t("common.saving") : t("agents.cofferConnection.disconnect")
        }
        pending={mutate.isPending}
        onConfirm={() => run(false)}
      />
    </div>
  );
}

/** At-a-glance state for the agents-table "Coffer" column. */
export function AgentConnectionBadge({ uid }: { uid: string }) {
  const { t } = useTranslation();
  const status = useAgentConnection(uid);
  if (status.isPending) {
    return <Skeleton className="h-5 w-20" aria-label={t("agents.cofferConnection.checking")} />;
  }
  const state = status.data?.state ?? "disconnected";
  return (
    <Badge
      variant={state === "connected" ? "secondary" : "outline"}
      className={state === "partial" ? "text-status-warn" : undefined}
    >
      {t(stateLabel(state))}
    </Badge>
  );
}
