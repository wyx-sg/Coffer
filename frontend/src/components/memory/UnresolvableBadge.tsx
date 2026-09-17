// frontend/src/components/memory/UnresolvableBadge.tsx
//
// The one mark a partition wears when the repository it is keyed on is no
// longer on disk (spec memory FR-016). Rendered identically on the list row and
// on the detail header, so the same fact never reads as two different things.
//
// Such a partition is delivered to NOBODY: nothing resolves to it any more, and
// its notes reach no session. That is precisely why it is marked rather than
// filtered out — deleting it is the developer's decision, and a partition
// missing from the list is a decision they can never make.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function UnresolvableBadge() {
  const { t } = useTranslation();
  return (
    <Tooltip>
      {/* The span is the trigger, not the Badge: Badge is a plain function
          component, so Radix has nothing to anchor the tooltip to if it is
          handed the ref. `tabIndex` keeps the hint reachable from the keyboard,
          which a hover-only mark would not be. */}
      <TooltipTrigger asChild>
        <span tabIndex={0} className="inline-flex shrink-0 rounded-full">
          <Badge
            variant="outline"
            data-testid="partition-unresolvable-badge"
            className="cursor-default border-status-warn/40 text-status-warn"
          >
            {t("memory.cols.unresolvable")}
          </Badge>
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{t("memory.cols.unresolvableHint")}</TooltipContent>
    </Tooltip>
  );
}
