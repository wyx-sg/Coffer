// frontend/src/components/agents/AgentCofferHookStatus.tsx — spec
// agent-registry "List every hook in the agent's native config".
//
// One line above the Hooks tab's list: the health of Coffer's own delivery hook
// (current / out of date / missing) and when it last fired. An out-of-date or
// missing hook offers Repair, which runs "Connect to Coffer" — connecting
// reinstalls every part, the hook included. Which command is installed versus
// the one Coffer would write lives behind the "?".
import { useTranslation } from "react-i18next";
import { Wrench } from "lucide-react";

import { HelpTip } from "@/components/HelpTip";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import type { CofferHook } from "@/lib/api/agents";
import { useAgentConnect } from "@/lib/hooks/useAgents";
import { toneClass, type Tone } from "@/lib/statusColors";
import { cn, formatDateTime } from "@/lib/utils";

const HEALTH_TONE: Record<CofferHook["health"], Tone> = {
  current: "ok",
  stale: "warn",
  missing: "error",
};

interface Props {
  agentUid: string;
  hook: CofferHook;
}

export function AgentCofferHookStatus({ agentUid, hook }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const connect = useAgentConnect(agentUid);
  const needsRepair = hook.health !== "current";

  const repair = () =>
    connect.mutate(true, {
      onSuccess: () => toast.success(t("agents.hooksTab.cofferHook.repaired")),
    });

  return (
    <Card className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 text-sm">
      <span className="font-medium">{t("agents.hooksTab.cofferHook.title")}</span>
      <span
        className={cn(
          "inline-flex items-center rounded-sm px-1.5 py-0.5 text-xs font-medium",
          toneClass(HEALTH_TONE[hook.health]),
        )}
      >
        {t(`agents.hooksTab.cofferHook.health.${hook.health}`)}
      </span>
      <span className="text-muted-foreground">
        {hook.last_fired_at
          ? t("agents.hooksTab.cofferHook.lastFired", {
              time: formatDateTime(hook.last_fired_at),
            })
          : t("agents.hooksTab.cofferHook.neverFired")}
      </span>
      <HelpTip label={t("agents.hooksTab.cofferHook.helpLabel")}>
        <p>{t("agents.hooksTab.cofferHook.help", { event: hook.event })}</p>
        <p className="break-all font-mono">{hook.path}</p>
        <p>{t("agents.hooksTab.cofferHook.expected")}</p>
        <p className="break-all font-mono">{hook.expected_command}</p>
        {hook.installed_command && hook.installed_command !== hook.expected_command ? (
          <>
            <p>{t("agents.hooksTab.cofferHook.installed")}</p>
            <p className="break-all font-mono">{hook.installed_command}</p>
          </>
        ) : null}
      </HelpTip>
      {needsRepair ? (
        <Button
          size="sm"
          variant="outline"
          className="ml-auto"
          disabled={connect.isPending}
          onClick={repair}
        >
          <Wrench className="mr-1.5 size-3.5" />
          {connect.isPending ? t("common.saving") : t("agents.hooksTab.cofferHook.repair")}
        </Button>
      ) : null}
    </Card>
  );
}
