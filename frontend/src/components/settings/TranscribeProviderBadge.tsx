// frontend/src/components/settings/TranscribeProviderBadge.tsx
// The one "Speech to text" pill for a model connection, rendered identically on
// the list row and the detail header — the twin of ActiveProviderBadge.
//
// It is read-only here, and set where every other fact about Coffer's own
// engine is set (Settings → Coffer's model). It earns a place on the connection library
// all the same, because this flag has no fallback: exactly one connection
// carries transcription and every voice message goes to that endpoint, so
// "which one?" is a question the library must be able to answer without a trip
// to Settings. Neutral rather than status-toned — it says where speech goes,
// not that anything is healthy.
import { useTranslation } from "react-i18next";
import { Mic } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export function TranscribeProviderBadge() {
  const { t } = useTranslation();
  // A local provider so the badge also works on surfaces rendered outside the
  // app shell (tests, dialogs); nesting inside Layout's provider is harmless.
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          {/* Focusable so the hint is reachable from the keyboard; Radix wires
              the tooltip text up as the trigger's description. */}
          <Badge variant="secondary" tabIndex={0} className="cursor-default gap-1">
            <Mic className="size-3" aria-hidden />
            {t("settings.connections.transcribe")}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>{t("settings.connections.transcribeHint")}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
