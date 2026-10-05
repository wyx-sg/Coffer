// frontend/src/components/memory/MemoryHeaderStatus.tsx
//
// The quiet line before the Memory header's read control (designs 5.2.01,
// 5.2.02, 5.2.12): "Reads automatically every hour · 14 min ago" (just "Read
// 14 min ago" with automatic reading off), "· 1 agent failed" when the last read left an
// agent unread (spec memory "Report the last read of the agents' memory"), and
// while Update memory runs, "Reading agents' memory…" then "Distilling 2 of 5
// partitions" (spec memory "Show Update memory's progress").
import { useTranslation } from "react-i18next";

import { cadenceName } from "@/components/upkeep/AutomaticPopover";
import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { useInternalEngineConfig } from "@/lib/hooks/useInternalEngine";
import { useMemoryReading } from "@/lib/hooks/useMemory";
import { useUpkeepRun } from "@/lib/hooks/useUpkeep";

/** The run Update memory holds while it works (backend `UPDATE_RUN`). */
const UPDATE_RUN = "update";

/** Whether Update memory is running right now, by anyone's request. */
export function useMemoryUpdateRunning(): boolean {
  return useUpkeepRun("memory", UPDATE_RUN) !== null;
}

export function MemoryHeaderStatus() {
  const { t, i18n } = useTranslation();
  const run = useUpkeepRun("memory", UPDATE_RUN);
  const reading = useMemoryReading();
  const { data: config } = useInternalEngineConfig();
  const read = config?.upkeep?.aggregate;
  const distil = config?.upkeep?.distil;
  // Automatic reading is on only when both passes are (see MemoryAutomaticPopover).
  const auto = Boolean(read?.enabled && (distil?.enabled ?? true));

  let text: string | null = null;
  if (run) {
    text =
      run.total === null || run.total === undefined || run.done === null || run.done === undefined
        ? t("memory.status.reading")
        : t("memory.status.distilling", {
            current: Math.min(run.done + 1, run.total),
            total: run.total,
          });
  } else if (reading.data?.read_at) {
    const when = formatRelativeTime(reading.data.read_at, i18n.language);
    text =
      auto && read
        ? t("memory.status.readAuto", { cadence: cadenceName(t, read), when })
        : t("memory.status.read", { when });
    const failed = reading.data.failures.length;
    if (failed > 0) text += ` · ${t("memory.status.failed", { count: failed })}`;
  }
  if (!text) return null;
  return (
    <span className="text-xs text-text-muted" data-testid="memory-status">
      {text}
    </span>
  );
}
