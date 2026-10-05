// frontend/src/components/memory/MemoryHeaderStatus.tsx
//
// The quiet line before the Memory header's read control while Update memory
// runs: "Reading agents' memory…" then "Distilling 2 of 5 partitions" (spec
// memory "Show Update memory's progress"). Idle, it shows nothing — the
// schedule is behind Update memory's ▾, and an agent the last read missed is
// the banner's (MemoryReadFailures).
import { useTranslation } from "react-i18next";

import { useUpkeepRun } from "@/lib/hooks/useUpkeep";

/** The run Update memory holds while it works (backend `UPDATE_RUN`). */
const UPDATE_RUN = "update";

/** Whether Update memory is running right now, by anyone's request. */
export function useMemoryUpdateRunning(): boolean {
  return useUpkeepRun("memory", UPDATE_RUN) !== null;
}

export function MemoryHeaderStatus() {
  const { t } = useTranslation();
  const run = useUpkeepRun("memory", UPDATE_RUN);
  if (!run) return null;
  const text =
    run.total === null || run.total === undefined || run.done === null || run.done === undefined
      ? t("memory.status.reading")
      : t("memory.status.distilling", {
          current: Math.min(run.done + 1, run.total),
          total: run.total,
        });
  return (
    <span className="text-xs text-text-muted" data-testid="memory-status">
      {text}
    </span>
  );
}
