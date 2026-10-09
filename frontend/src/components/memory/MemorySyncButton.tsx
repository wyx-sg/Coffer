// frontend/src/components/memory/MemorySyncButton.tsx
//
// The Memory header's one primary control (spec memory "Sync on an interval and
// on demand"): **Sync now** on the main half — "Syncing…" while a sync runs,
// whoever started it (the daemon's state says so, so leaving mid-sync and
// coming back still reads busy) — and on the ▾ half the automatic sync: its
// switch and interval, the internal engine's `memory_sync` pass, saved as they
// change (the shared AutomaticPopover, board 5.2.04).
import { ChevronDown, LoaderCircle, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AutomaticPopover, clockLine } from "@/components/upkeep/AutomaticPopover";
import { Button } from "@/components/ui/button";
import { useInternalEngineConfig, useSetUpkeep } from "@/lib/hooks/useInternalEngine";
import { useSyncNow } from "@/lib/hooks/useMemory";

interface Props {
  /** A sync the daemon reports as running. */
  running: boolean;
}

export function MemorySyncButton({ running }: Props) {
  const { t, i18n } = useTranslation();
  const sync = useSyncNow();
  const { data: config } = useInternalEngineConfig();
  const setUpkeep = useSetUpkeep();
  const setting = config?.upkeep?.memory_sync;
  const busy = sync.isPending || running;

  const main = (
    <Button
      type="button"
      onClick={() => sync.mutate()}
      disabled={busy}
      className={setting ? "rounded-r-none" : undefined}
    >
      {busy ? <LoaderCircle className="animate-spin" aria-hidden /> : <RefreshCw aria-hidden />}
      {busy ? t("memory.syncing") : t("memory.syncNow")}
    </Button>
  );
  if (!setting) return main;
  return (
    <div className="inline-flex">
      {main}
      <AutomaticPopover
        title={t("memory.automatic.title")}
        description={t("memory.automatic.description")}
        setting={setting}
        busy={setUpkeep.isPending}
        onToggle={(enabled) => setUpkeep.mutate({ pass: "memory_sync", enabled })}
        onInterval={(interval_s) => setUpkeep.mutate({ pass: "memory_sync", interval_s })}
        clock={clockLine(
          t,
          i18n.language,
          setting,
          "memory.automatic.last",
          "memory.automatic.never",
        )}
        trigger={
          <Button
            type="button"
            aria-label={t("memory.automatic.title")}
            aria-haspopup="dialog"
            data-testid="memory-automatic"
            className="w-7 rounded-l-none border-l-accent-foreground/30 px-0"
          >
            <ChevronDown aria-hidden className="!size-3" />
          </Button>
        }
      />
    </div>
  );
}
