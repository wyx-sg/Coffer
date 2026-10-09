// frontend/src/components/memory/MemorySyncClock.tsx
//
// The Memory header's subtitle (spec memory "Manage memory sync in the web
// UI and on the command line"): when memory last synced on this machine and when it syncs next —
// "Last synced 14 min ago · next in 46 min" — or that automatic sync is off.
// The next run is the internal engine's clock for the `memory_sync` pass; the
// last is the sync's own ledger, whoever asked for it.
import { useTranslation } from "react-i18next";

import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { useInternalEngineConfig } from "@/lib/hooks/useInternalEngine";

interface Props {
  /** When the last sync finished; empty when this machine never synced. */
  lastSyncedAt: string;
  running: boolean;
}

export function MemorySyncClock({ lastSyncedAt, running }: Props) {
  const { t, i18n } = useTranslation();
  const setting = useInternalEngineConfig().data?.upkeep?.memory_sync;
  const parts = [
    running
      ? t("memory.clock.running")
      : lastSyncedAt
        ? t("memory.clock.last", { when: formatRelativeTime(lastSyncedAt, i18n.language) })
        : t("memory.clock.never"),
  ];
  if (setting && !setting.enabled) parts.push(t("memory.clock.off"));
  else if (setting?.next_pass_at && !running) {
    parts.push(t("upkeep.next", { when: formatRelativeTime(setting.next_pass_at, i18n.language) }));
  }
  return <span data-testid="memory-sync-clock">{parts.join(" · ")}</span>;
}
