// frontend/src/pages/MemoryPage.tsx — the Memory overview (spec memory "Present a
// partition as its memories", web-ui "Show memory delivery on the Memory page").
//
// Memory is read-only: Coffer reads each agent's own memory and distils it into
// one memory per subject, in partitions — `global` plus one per repository
// (ADR aggregate-agent-memory-never-write-it). Nothing here is user-created,
// so the header's one action is Update memory: read every agent's latest
// memory and distil what is new (spec memory "Update memory in one action").
//
// Two blocks. "Delivered at session start" shows, per agent and over the last
// seven days, how often memory was delivered and how many memories were read —
// with no hook detail: the hook's state and Repair live only on the agent's
// page. "Partitions" is the table, or the first-run state while there are
// none. The audit trail is the Activity page's, not duplicated here.
import { useTranslation } from "react-i18next";
import { Brain } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { MemoryDeliveriesSection } from "@/components/memory/MemoryDeliveriesSection";
import { MemoryPartitionsTable } from "@/components/memory/MemoryPartitionsTable";
import { MemorySection } from "@/components/memory/MemorySection";
import { MemoryUpdateButton } from "@/components/memory/MemoryUpdateButton";
import { MemoryWelcomePanel } from "@/components/memory/MemoryWelcomePanel";
import { PageHeader } from "@/components/PageHeader";
import { translateApiError } from "@/lib/api/errors";
import { useMemoryPartitions } from "@/lib/hooks/useMemory";

export function MemoryPage() {
  const { t } = useTranslation();
  const { data: partitions, isPending, error } = useMemoryPartitions();
  const rows = partitions ?? [];
  const memories = rows.reduce((sum, p) => sum + p.note_count, 0);
  const firstRun = !isPending && !error && rows.length === 0;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Brain}
        title={t("memory.title")}
        subtitle={t("memory.subtitle")}
        actions={
          // On the first run the welcome carries the same button; two of them
          // would be the page asking twice.
          firstRun ? null : <MemoryUpdateButton variant="outline" />
        }
      />

      <MemoryDeliveriesSection />

      <MemorySection
        title={t("memory.partitions.title")}
        meta={
          rows.length > 0
            ? `${t("memory.partitions.count", { count: rows.length })} · ${t(
                "memory.partitions.memories",
                { count: memories },
              )}`
            : undefined
        }
        testId="memory-partitions"
      >
        {error ? (
          <EmptyState
            icon={Brain}
            tone="error"
            title={t("memory.loadFailed")}
            description={translateApiError(t, error)}
          />
        ) : firstRun ? (
          <MemoryWelcomePanel />
        ) : (
          <MemoryPartitionsTable rows={rows} isLoading={isPending} />
        )}
      </MemorySection>
    </div>
  );
}
