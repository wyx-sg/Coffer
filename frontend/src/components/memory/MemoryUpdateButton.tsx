// frontend/src/components/memory/MemoryUpdateButton.tsx
//
// The one memory action (spec memory "Update memory in one action"): read every
// agent's latest native memory, then distil what is new into Coffer's memories.
// The partitions page, a partition's page and the first-run welcome all carry
// this same button. There used to be two — "Read from agents" (aggregation) on
// the list and "Distil" on a partition — and either one alone left the notes
// stale, so one request (`POST /memory/sync`) now does both and one button
// asks for it. On the list page and the first run it is the page's one primary
// button (refresh icon); on a partition's page it is a secondary button with
// the wand (boards 5.2.01, 5.2.06). No tooltip: the label says what it does.
//
// With `schedule` (the list page) it is a split button: the ▾ half opens the
// automatic-read schedule (the same read the main half runs on request), so
// everything about reading sits in one control.
import { useTranslation } from "react-i18next";
import { ChevronDown, LoaderCircle, RefreshCw, WandSparkles } from "lucide-react";

import { MemoryAutomaticPopover } from "@/components/memory/MemoryAutomaticPopover";
import { Button } from "@/components/ui/button";
import { useInternalEngineConfig } from "@/lib/hooks/useInternalEngine";
import { useSyncMemory } from "@/lib/hooks/useMemory";

interface Props {
  /** A pass the daemon reports as running (e.g. a distil over the partition on
   *  screen). Spins the button and holds it disabled even when this page did
   *  not start the pass — leaving mid-pass and coming back must not invite a
   *  second one. */
  running?: boolean;
  variant?: "default" | "outline";
  size?: "default" | "sm";
  /** Add the ▾ half that opens the automatic-read schedule. */
  schedule?: boolean;
}

export function MemoryUpdateButton({
  running = false,
  variant = "default",
  size,
  schedule = false,
}: Props) {
  const { t } = useTranslation();
  const { data: config } = useInternalEngineConfig();
  const hasSchedule = schedule && Boolean(config?.upkeep?.aggregate);
  const update = useSyncMemory();
  const busy = update.isPending || running;
  const Icon = busy ? LoaderCircle : variant === "outline" ? WandSparkles : RefreshCw;

  const main = (
    <Button
      type="button"
      variant={variant}
      size={size}
      onClick={() => update.mutate()}
      disabled={busy}
      className={hasSchedule ? "rounded-r-none" : undefined}
    >
      <Icon className={busy ? "animate-spin" : undefined} aria-hidden />
      {busy ? t("memory.updating") : t("memory.update")}
    </Button>
  );
  if (!hasSchedule) return main;
  return (
    <div className="inline-flex">
      {main}
      <MemoryAutomaticPopover
        trigger={
          <Button
            type="button"
            variant={variant}
            size={size}
            aria-label={t("memory.automatic.title")}
            aria-haspopup="dialog"
            data-testid="memory-automatic"
            className="rounded-l-none border-l-accent-foreground/30 px-0 w-7"
          >
            <ChevronDown aria-hidden className="!size-3" />
          </Button>
        }
      />
    </div>
  );
}
