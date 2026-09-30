// frontend/src/components/memory/MemoryUpdateButton.tsx
//
// The one memory action (spec memory "Update memory in one action"): read every
// agent's latest native memory, then distil what is new into Coffer's memories.
// The partitions page, a partition's page and the first-run welcome all carry
// this same button. There used to be two — "Read from agents" (aggregation) on
// the list and "Distil" on a partition — and either one alone left the notes
// stale, so one request (`POST /memory/sync`) now does both and one button
// asks for it.
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useSyncMemory } from "@/lib/hooks/useMemory";
import { cn } from "@/lib/utils";

interface Props {
  /** A pass the daemon reports as running (e.g. a distil over the partition on
   *  screen). Spins the button and holds it disabled even when this page did
   *  not start the pass — leaving mid-pass and coming back must not invite a
   *  second one. */
  running?: boolean;
  variant?: "default" | "outline";
  size?: "default" | "sm";
}

export function MemoryUpdateButton({ running = false, variant = "default", size }: Props) {
  const { t } = useTranslation();
  const update = useSyncMemory();
  const busy = update.isPending || running;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant={variant}
          size={size}
          onClick={() => update.mutate()}
          disabled={busy}
        >
          <RefreshCw className={cn("mr-1.5 size-4", busy && "animate-spin")} aria-hidden />
          {busy ? t("memory.updating") : t("memory.update")}
        </Button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{t("memory.updateHint")}</TooltipContent>
    </Tooltip>
  );
}
