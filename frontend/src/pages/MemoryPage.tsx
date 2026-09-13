// frontend/src/pages/MemoryPage.tsx — the Memory surface (spec memory FR-062).
//
// Lists partitions: `global` plus one per project, aggregated read-only from
// the agents' own native memories (ADR aggregate-agent-memory-never-write-it)
// — nothing here is user-created, so Sync (not "Add") is the header action.
// Delivery state and the audit log are not partition-scoped, so they render
// once above the table rather than per-partition (the detail page owns facts,
// conflicts and per-fact overrides for one partition).
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Brain, RefreshCw } from "lucide-react";

import { MemoryAuditLog } from "@/components/memory/MemoryAuditLog";
import { MemoryDeliveryPanel } from "@/components/memory/MemoryDeliveryPanel";
import {
  MemoryPartitionsTable,
  type MemoryPartitionRow,
} from "@/components/memory/MemoryPartitionsTable";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMemoryPartitions, useSyncMemory } from "@/kinds/memory/useMemory";
import { useResources } from "@/lib/hooks/useResources";
import { translateApiError } from "@/lib/api/errors";

export function MemoryPage() {
  const { t } = useTranslation();
  const { data: partitions, isPending, error } = useMemoryPartitions();
  const { data: resources } = useResources("memory");
  const sync = useSyncMemory();

  const rows: MemoryPartitionRow[] = useMemo(() => {
    const byName = new Map((resources ?? []).map((r) => [r.name, r]));
    return (partitions ?? []).map((p) => {
      const resource = byName.get(p.name);
      return {
        ...p,
        enabled: resource?.enabled ?? true,
        scope: resource?.scope ?? null,
      };
    });
  }, [partitions, resources]);

  const hasRows = rows.length > 0;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Brain}
        title={t("memory.title")}
        subtitle={t("memory.subtitle")}
        actions={
          <Button onClick={() => sync.mutate()} disabled={sync.isPending}>
            <RefreshCw className={sync.isPending ? "mr-1 size-4 animate-spin" : "mr-1 size-4"} />
            {sync.isPending ? t("memory.syncing") : t("memory.sync")}
          </Button>
        }
      />

      <MemoryDeliveryPanel />

      {isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      ) : error ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">{t("memory.loadFailed")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : !hasRows ? (
        <Card>
          <CardContent className="space-y-3 py-8 text-center">
            <p className="text-muted-foreground">{t("memory.empty")}</p>
            <Button variant="outline" onClick={() => sync.mutate()} disabled={sync.isPending}>
              {t("memory.sync")}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <MemoryPartitionsTable rows={rows} />
      )}

      <MemoryAuditLog />
    </div>
  );
}
