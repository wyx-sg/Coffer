// frontend/src/pages/MemoryPage.tsx — the Memory overview (spec memory "Show a partition's memories read-only").
//
// Coffer reads each agent's own memory and distils it into
// one memory per subject, in partitions — `global` plus one per repository
// (ADR aggregate-agent-memory-never-write-it). Nothing here is user-created (a person only edits a memory's body),
// so the header groups its controls in two: Tidy all (hands every partition to
// the default managed agent and sends the prompt at once; spec memory "Hand a
// partition's tidying to the agent") on the left, then, after a divider, the
// read group — a quiet line saying when the agents' memory was last read (and
// that it is read automatically), or how far Update memory is, and Update
// memory itself, the page's one primary button, a split button whose ▾ opens
// the automatic-read schedule (spec memory "Update memory in one action"). When
// the last read left an agent unread,
// a banner above the blocks says so. Boards 5.2.01–5.2.04, 5.2.10 and 5.2.11.
//
// The body is the partitions table, untitled, or the first-run state while
// there are none. The audit trail is the Activity page's, not duplicated here.
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Brain } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { MemoryHeaderStatus, useMemoryUpdateRunning } from "@/components/memory/MemoryHeaderStatus";
import { MemoryReadFailures } from "@/components/memory/MemoryReadFailures";
import { MemoryPartitionsTable } from "@/components/memory/MemoryPartitionsTable";
import { MemoryUpdateButton } from "@/components/memory/MemoryUpdateButton";
import { MemoryWelcomePanel } from "@/components/memory/MemoryWelcomePanel";
import { ExperimentalTag } from "@/components/ExperimentalTag";
import { PageHeader } from "@/components/PageHeader";
import { translateApiError } from "@/lib/api/errors";
import { getTidyHandoff } from "@/lib/api/memory";
import { useDaemonEvents } from "@/lib/hooks/useDaemonEvents";
import { memoryKey } from "@/lib/api/queryKeys";
import { useMemoryPartitions } from "@/lib/hooks/useMemory";

/** Tidy all's prompt, asked of the daemon when the button is pressed. */
const tidyAllPrompt = () => getTidyHandoff().then((handoff) => handoff.prompt);

export function MemoryPage() {
  const { t } = useTranslation();
  const { data: partitions, isPending, error } = useMemoryPartitions();
  const rows = partitions ?? [];
  const firstRun = !isPending && !error && rows.length === 0;
  const updating = useMemoryUpdateRunning();
  // A distil pass or a read finishing emits a memory change event: refetch
  // everything read under memoryKey instead of waiting for a window focus.
  const qc = useQueryClient();
  useDaemonEvents({
    onMessage: (m) => {
      if (m.type === "change" && m.change.kind === "memory") {
        void qc.invalidateQueries({ queryKey: memoryKey });
      }
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("memory.title")}
        badges={<ExperimentalTag />}
        subtitle={t("memory.subtitle")}
        actions={
          // On the first run the welcome carries the same button; two of them
          // would be the page asking twice.
          firstRun ? null : (
            <>
              <AgentHandoff prompt={tidyAllPrompt} label={t("memory.tidy.all")} help={false} />
              <span aria-hidden className="mx-1 h-5 w-px bg-border" />
              <MemoryHeaderStatus />
              <MemoryUpdateButton running={updating} schedule />
            </>
          )
        }
      />

      {firstRun ? null : <MemoryReadFailures />}

      {firstRun ? (
        <MemoryWelcomePanel />
      ) : (
        <div data-testid="memory-partitions">
          {error ? (
            <EmptyState
              icon={Brain}
              tone="error"
              title={t("memory.loadFailed")}
              description={translateApiError(t, error)}
            />
          ) : (
            <MemoryPartitionsTable rows={rows} isLoading={isPending} />
          )}
        </div>
      )}
    </div>
  );
}
