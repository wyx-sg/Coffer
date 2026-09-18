// frontend/src/pages/MemoryPage.tsx — the Memory surface (spec memory FR-037).
//
// Lists partitions: `global` plus one per repository, distilled from the
// agents' own native memories, which Coffer only ever reads (ADR
// aggregate-agent-memory-never-write-it) — nothing here is user-created, so
// "Read from agents" (not "Add") is the header action. It is not called Sync: that name belongs to the vault-sync
// page, and this action reads the agents' native memory rather than converging
// anything with a remote.
//
// An EMPTY vault gets the welcome panel every other first-run surface gives —
// skills, knowledge, agents, channels, providers — so arriving at an empty
// Memory reads like arriving at an empty anything else. Once a partition
// exists it is the table, and the table's own empty row covers a search that
// matched nothing. (The run context table inside a run is the other way round
// on purpose: there the columns say what a run can be MADE of, which is worth
// seeing before anything is in it.)
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
import { MemoryWelcomePanel } from "@/components/memory/MemoryWelcomePanel";
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

  // Merged on the uid, which both reads carry: on the name the join would hold
  // only for as long as nothing was renamed between the two requests.
  const rows: MemoryPartitionRow[] = useMemo(() => {
    const byUid = new Map((resources ?? []).map((r) => [r.uid, r]));
    return (partitions ?? []).map((p) => {
      const resource = byUid.get(p.uid);
      // `enabled` alone: the `memory` kind declares no per-agent scope, so
      // there is no second Resource field for a row to carry.
      return { ...p, enabled: resource?.enabled ?? true };
    });
  }, [partitions, resources]);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Brain}
        title={t("memory.title")}
        subtitle={t("memory.subtitle")}
        actions={
          // Only once there is something to re-read: on an empty vault the
          // welcome panel carries the same button, and two of them would be
          // the page asking twice.
          rows.length > 0 ? (
            <Button onClick={() => sync.mutate()} disabled={sync.isPending}>
              <RefreshCw className={sync.isPending ? "mr-1 size-4 animate-spin" : "mr-1 size-4"} />
              {sync.isPending ? t("memory.reading") : t("memory.readFromAgents")}
            </Button>
          ) : null
        }
      />

      {/* The header stays mounted through loading — the table renders skeleton
          rows under it rather than the page swapping to a loading card. */}
      {error ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">{t("memory.loadFailed")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : !isPending && rows.length === 0 ? (
        <MemoryWelcomePanel onRead={() => sync.mutate()} reading={sync.isPending} />
      ) : (
        <MemoryPartitionsTable rows={rows} isLoading={isPending} />
      )}
    </div>
  );
}
