// src/components/providers/CofferUseBadge.tsx — the badge that says Coffer ITSELF runs on a provider.
//
// The `internal_default` provider carries "Coffer · background model", the
// `transcribe_default` one "Coffer · speech to text" (spec provider-switching
// "Offer every connection operation on REST and the web"). Each flag sits on
// one provider with no fallback, so the library must answer "which one does
// Coffer use?" without a trip to Settings. In the narrow list pane the badge
// is a small chip beside the agent marks; its name is its accessible label and
// its tooltip, which also says where it is changed: Settings › General.
import { useTranslation } from "react-i18next";
import { Cpu, Mic } from "lucide-react";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export type CofferUse = "engine" | "transcribe";

const ICON = { engine: Cpu, transcribe: Mic } as const;

export function CofferUseBadge({ use }: { use: CofferUse }) {
  const { t } = useTranslation();
  const Icon = ICON[use];
  const label = t(`providers.cofferUse.${use}`);
  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            role="img"
            aria-label={label}
            className="inline-flex h-[18px] w-[22px] shrink-0 items-center justify-center rounded-sm bg-chip text-text-muted"
          >
            <Icon className="size-3" aria-hidden />
          </span>
        </TooltipTrigger>
        <TooltipContent>
          <span className="font-label">{label}</span> — {t(`providers.cofferUse.${use}Hint`)}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
