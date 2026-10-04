// src/components/RelativeTime.tsx — a time the way lists print it (Foundations 0.3.03).
//
// "12 min ago" / "Yesterday" / "Sep 29" in the page, and the exact local time
// to the second on hover and focus — the tooltip only restates the full value,
// so it is allowed on a plain text. Mono-free and tabular so a column of them
// lines up.
import { useTranslation } from "react-i18next";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { formatExact, formatRelative } from "@/lib/time";
import { cn } from "@/lib/utils";

interface Props {
  /** An ISO timestamp (or a Date). */
  iso: string | Date;
  className?: string;
}

export function RelativeTime({ iso, className }: Props) {
  const { t, i18n } = useTranslation();
  const date = typeof iso === "string" ? new Date(iso) : iso;
  const valid = !Number.isNaN(date.getTime());
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <time
            dateTime={valid ? date.toISOString() : undefined}
            tabIndex={0}
            className={cn("tabular-nums", className)}
          >
            {formatRelative(date, i18n.language, t)}
          </time>
        </TooltipTrigger>
        {valid ? <TooltipContent>{formatExact(date, i18n.language)}</TooltipContent> : null}
      </Tooltip>
    </TooltipProvider>
  );
}
