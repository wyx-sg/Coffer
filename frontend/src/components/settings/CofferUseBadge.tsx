// frontend/src/components/settings/CofferUseBadge.tsx
// The pills that say a model connection is used by Coffer ITSELF — for its
// background passes (the `internal_default` connection) or to transcribe voice
// (the `transcribe_default` connection) — rendered identically on the list row
// and the detail header, twins of ActiveProviderBadge.
//
// Both are read-only here and set in Settings → Coffer's model. They earn a
// place on the connection library all the same: each flag sits on exactly one
// connection with no fallback, so "which one does Coffer use?" is a question
// the library must answer without a trip to Settings. The label leads with
// "Coffer" because a bare "Speech to text" reads as a capability of the
// provider rather than a job Coffer gives it. Neutral rather than status-toned
// — they say where Coffer's own work goes, not that anything is healthy.
import { useTranslation } from "react-i18next";
import { Cpu, Mic } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export type CofferUse = "engine" | "transcribe";

const ICON = { engine: Cpu, transcribe: Mic } as const;

export function CofferUseBadge({ use }: { use: CofferUse }) {
  const { t } = useTranslation();
  const Icon = ICON[use];
  // A local provider so the badge also works on surfaces rendered outside the
  // app shell (tests, dialogs); nesting inside Layout's provider is harmless.
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          {/* Focusable so the hint is reachable from the keyboard; Radix wires
              the tooltip text up as the trigger's description. */}
          <Badge variant="secondary" tabIndex={0} className="cursor-default gap-1">
            <Icon className="size-3" aria-hidden />
            {t(`settings.connections.cofferUse.${use}`)}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>{t(`settings.connections.cofferUse.${use}Hint`)}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
