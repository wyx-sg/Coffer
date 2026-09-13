// frontend/src/components/memory/MemoryDeliveryPanel.tsx
//
// Per-agent delivery state (spec memory FR-054/FR-055, ADR
// aggregate-agent-memory-never-write-it). This is the surface the removed
// injection layer never had: it shipped a working hook that was never once
// installed, and nothing said so for two months. So the signal here is NOT
// "installed" — it is "installed" is dead-highlighted with a warning until
// `last_fired_at` is non-empty, because a hook that never fires is
// indistinguishable from no feature at all.
//
// Delivery is not partition-scoped (it lives in an agent's own settings, not
// under any one partition's directory), so this renders once, above the
// partitions table, rather than per-partition.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { DeliveryStatusOut } from "@/kinds/memory/types";
import { useInstallDelivery, useMemoryDelivery, useRemoveDelivery } from "@/kinds/memory/useMemory";

function DeliveryRow({ status }: { status: DeliveryStatusOut }) {
  const { t } = useTranslation();
  const install = useInstallDelivery();
  const remove = useRemoveDelivery();
  const [confirmingRemove, setConfirmingRemove] = useState(false);

  const neverFired = status.installed && !status.last_fired_at;
  const busy = install.isPending || remove.isPending;

  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 py-3 last:border-0"
      data-testid={`memory-delivery-row-${status.agent}`}
    >
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">{status.agent}</span>
          {status.installed ? (
            neverFired ? (
              <Badge
                variant="outline"
                className="gap-1 border-status-warn/40 bg-status-warn/10 text-status-warn"
                data-testid={`memory-delivery-warning-${status.agent}`}
              >
                <AlertTriangle className="size-3" aria-hidden />
                {t("memory.delivery.neverFired")}
              </Badge>
            ) : (
              <Badge variant="outline" className="gap-1 bg-status-ok/10 text-status-ok">
                <CheckCircle2 className="size-3" aria-hidden />
                {t("memory.delivery.installed")}
              </Badge>
            )
          ) : (
            <Badge variant="outline" className="text-muted-foreground">
              {t("memory.delivery.notInstalled")}
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {status.installed
            ? neverFired
              ? t("memory.delivery.neverFiredHint", { event: status.event })
              : t("memory.delivery.lastFiredAt", {
                  event: status.event,
                  time: new Date(status.last_fired_at).toLocaleString(),
                })
            : t("memory.delivery.notInstalledHint")}
        </p>
      </div>

      {status.installed ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
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

export function MemoryDeliveryPanel() {
  const { t } = useTranslation();
  const { data, isPending, error } = useMemoryDelivery();
  const rows = data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("memory.delivery.title")}</CardTitle>
        <p className="text-sm text-muted-foreground">{t("memory.delivery.subtitle")}</p>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : error ? (
          <p className="text-sm text-destructive">{t("memory.delivery.loadFailed")}</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("memory.delivery.empty")}</p>
        ) : (
          rows.map((r) => <DeliveryRow key={r.agent} status={r} />)
        )}
      </CardContent>
    </Card>
  );
}
