// src/components/providers/CofferUseBadge.tsx — the badge that says Coffer ITSELF runs on a provider.
//
// The `transcribe_default` provider carries "Coffer · speech to text" (spec
// provider-switching "Offer every connection operation over REST and in the
// web UI"). The flag sits on one provider, so the library must answer "which
// one does Coffer use?" without a trip to Settings. In the narrow list pane the badge
// is a small chip beside the agent marks; its name is its accessible label and
// its tooltip, which also says where it is changed: Settings › General.
import { useTranslation } from "react-i18next";
import { Mic } from "lucide-react";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export type CofferUse = "transcribe";

const ICON = { transcribe: Mic } as const;

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
