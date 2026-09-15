// frontend/src/pages/MemoryPage.tsx — the Memory surface (spec memory FR-062).
//
// Lists partitions: `global` plus one per project, aggregated read-only from
// the agents' own native memories (ADR aggregate-agent-memory-never-write-it)
// — nothing here is user-created, so Sync (not "Add") is the header action.
//
// One table, always — the same shape whether the vault holds a hundred
// partitions or none, exactly like every other list page. An empty vault gets
// the table's own empty row, not a different page: a surface that changes
// shape with its data teaches the reader nothing about where things will be.
// Sync stays in the header, so it is reachable from the empty state too.
//
// Two things that used to render here have moved out. Per-agent DELIVERY is
// per-agent state — it installs a hook into one agent's own settings file — so
// it belongs on that agent's detail page (components/agents/AgentMemoryTab).
// The AUDIT LOG is the Activity page's Changes tab, which reads the whole
// vault's trail; a second kind-scoped copy here was a duplicate surface.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Brain, RefreshCw } from "lucide-react";

import {
  MemoryPartitionsTable,
  type MemoryPartitionRow,
} from "@/components/memory/MemoryPartitionsTable";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMemoryPartitions, useSyncMemory } from "@/lib/hooks/useMemory";
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
      ) : (
        // No zero-row branch: DataTable renders its header and its own empty
        // row, so "no partitions yet" is a line inside the table rather than
        // a card standing where the table would be.
        <MemoryPartitionsTable rows={rows} />
      )}
    </div>
  );
}
