// frontend/src/pages/MemoryPage.tsx — the Memory surface (spec memory
// "Present partitions as a table and a file tree").
//
// Lists partitions: `global` plus one per repository, distilled from the
// agents' own native memories, which Coffer only ever reads (ADR
// aggregate-agent-memory-never-write-it) — nothing here is user-created, so
// "Update memory" (not "Add") is the header action: read every agent's latest
// memory and distil what is new (spec memory "Update memory in one action").
// It is not called Sync: that name belongs to the vault-sync page, and this
// action reads the agents' native memory rather than converging anything with
// a remote.
//
// The table has no status column: every partition is served to every agent
// (spec memory "Serve every partition to every agent"), so this page reads
// only the partitions endpoint.
//
// An EMPTY vault gets the welcome panel every other first-run surface gives —
// skills, knowledge, agents, channels, providers — so arriving at an empty
// Memory reads like arriving at an empty anything else. Once a partition
// exists it is the table, and the table's own empty row covers a search that
// matched nothing.
//
// Two things that used to render here have moved out. Per-agent DELIVERY is
// per-agent state — it installs a hook into one agent's own settings file — so
// it belongs on that agent's detail page (components/agents/AgentMemoryTab).
// The AUDIT LOG is the Activity page's Changes tab, which reads the whole
// vault's trail; a second kind-scoped copy here was a duplicate surface.
import { useTranslation } from "react-i18next";
import { Brain } from "lucide-react";

import { MemoryPartitionsTable } from "@/components/memory/MemoryPartitionsTable";
import { MemoryUpdateButton } from "@/components/memory/MemoryUpdateButton";
import { MemoryWelcomePanel } from "@/components/memory/MemoryWelcomePanel";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMemoryPartitions } from "@/lib/hooks/useMemory";
import { translateApiError } from "@/lib/api/errors";

export function MemoryPage() {
  const { t } = useTranslation();
  const { data: partitions, isPending, error } = useMemoryPartitions();
  const rows = partitions ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Brain}
        title={t("memory.title")}
        subtitle={t("memory.subtitle")}
        actions={
          // Only once there is something to update: on an empty vault the
          // welcome panel carries the same button, and two of them would be
          // the page asking twice.
          rows.length > 0 ? <MemoryUpdateButton /> : null
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
        <MemoryWelcomePanel />
      ) : (
        <MemoryPartitionsTable rows={rows} isLoading={isPending} />
      )}
    </div>
  );
}
