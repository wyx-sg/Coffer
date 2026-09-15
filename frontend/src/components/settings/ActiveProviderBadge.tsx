// frontend/src/components/settings/ActiveProviderBadge.tsx
// The one "Active" pill for a model provider, rendered identically on the list
// row and the detail header. "Active" is a fact about Coffer's own engine
// (which connection its internal model runs on), not about the provider's
// reach, so the pill carries a tooltip saying exactly that — the word alone
// invites the reading "this one is switched on".
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { toneClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";

export function ActiveProviderBadge() {
  const { t } = useTranslation();
  const hint = t("settings.connections.activeHint");
  // A local provider so the badge also works on surfaces rendered outside the
  // app shell (tests, dialogs); nesting inside Layout's provider is harmless.
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          {/* Focusable so the hint is reachable from the keyboard; Radix wires
              the tooltip text up as the trigger's description. */}
          <Badge
            variant="outline"
            tabIndex={0}
            className={cn("cursor-default gap-1 border-transparent", toneClass("ok"))}
          >
            <Check className="size-3" aria-hidden />
            {t("settings.connections.active")}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>{hint}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
