// frontend/src/components/agents/AgentMemoryDelivery.tsx
//
// ONE agent's memory-delivery state (spec memory FR-032/FR-033, ADR
// aggregate-agent-memory-never-write-it), rendered on that agent's own detail
// page. Delivery installs a hook into THIS agent's own settings file, so it is
// per-agent state and belongs beside the agent — it used to sit on the
// standalone Memory page as a list with a row per agent, which put a per-agent
// act on a resource page and made the reader pick their agent out of a list
// they had already navigated past.
//
// Because the agent is fixed by the page, there is no picker here: the query
// is `GET /memory/delivery?agent=<name>`, which answers for that one agent.
//
// This card answers one question — is the hook written into that agent's
// settings or not. Whether it has actually fired is a stream of events, not a
// property of the agent, so it is read where every other stream of events is
// read: the Activity page's audit log, one entry per fire (spec memory FR-033).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { translateApiError } from "@/lib/api/errors";
import type { DeliveryStatusOut } from "@/lib/api/memoryTypes";
import { useInstallDelivery, useMemoryDelivery, useRemoveDelivery } from "@/lib/hooks/useMemory";

function DeliveryState({ status }: { status: DeliveryStatusOut }) {
  const { t } = useTranslation();
  const install = useInstallDelivery();
  const remove = useRemoveDelivery();
  const [confirmingRemove, setConfirmingRemove] = useState(false);

  const busy = install.isPending || remove.isPending;

  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3"
      data-testid={`memory-delivery-${status.agent}`}
    >
      <div className="min-w-0 space-y-1">
        <div className="flex items-center gap-2">
          {status.installed ? (
            <Badge variant="outline" className="gap-1 bg-status-ok/10 text-status-ok">
              <CheckCircle2 className="size-3" aria-hidden />
              {t("memory.delivery.installed")}
            </Badge>
          ) : (
            <Badge variant="outline" className="text-muted-foreground">
              {t("memory.delivery.notInstalled")}
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {status.installed
            ? t("memory.delivery.installedHint", { event: status.event })
            : t("memory.delivery.notInstalledHint")}
        </p>
      </div>

      {status.installed ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="shrink-0"
          disabled={busy}
          onClick={() => setConfirmingRemove(true)}
        >
          {t("memory.delivery.remove")}
        </Button>
      ) : (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="shrink-0"
          disabled={busy}
          onClick={() => install.mutate(status.agent)}
        >
          {t("memory.delivery.install")}
        </Button>
      )}

      <ConfirmDialog
        open={confirmingRemove}
        onOpenChange={setConfirmingRemove}
        title={t("memory.delivery.removeConfirmTitle")}
        description={t("memory.delivery.removeConfirmDescription", { agent: status.agent })}
        confirmLabel={t("memory.delivery.remove")}
        variant="default"
        pending={remove.isPending}
        onConfirm={() => {
          setConfirmingRemove(false);
          remove.mutate(status.agent);
        }}
      />
    </div>
  );
}

export function AgentMemoryDelivery({ agentName }: { agentName: string }) {
  const { t } = useTranslation();
  const { data, isPending, error } = useMemoryDelivery(agentName);
  // The by-agent query answers for exactly one agent; anything else is the
  // daemon disagreeing with its own contract, and is treated as "no state".
  const status = data?.[0];

  return (
    <Card className="space-y-3 p-4">
      <div className="space-y-1">
        <h3 className="text-sm font-medium text-muted-foreground">{t("memory.delivery.title")}</h3>
        <p className="text-xs text-muted-foreground">{t("memory.delivery.subtitle")}</p>
      </div>

      {isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : error ? (
        <p className="text-sm text-destructive">{translateApiError(t, error)}</p>
      ) : status ? (
        <DeliveryState status={status} />
      ) : (
        <p className="text-sm text-muted-foreground">{t("memory.delivery.unsupported")}</p>
      )}
    </Card>
  );
}
