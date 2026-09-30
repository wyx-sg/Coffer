// src/components/shell/AttentionDot.tsx — the count badge a sidebar entry carries while its kind needs the user.
//
// Expanded, a pill with the count, toned danger for a failure and warning for
// anything else (board 1.2.01). On the collapsed rail the words are gone, so
// it shrinks to a dot of the same tone riding the icon, and the row's tooltip
// carries the count (board 1.2.02). The accessible name says the entry needs
// attention; the count itself is the visible text.
import { useTranslation } from "react-i18next";

import type { AttentionTone } from "@/lib/hooks/useAttentionSignals";
import { cn } from "@/lib/utils";

interface Props {
  /** The entry's route, for the test id (`nav-dot-sync`). */
  entry: string;
  collapsed: boolean;
  /** How many things need the user; the rail shows a dot either way. */
  count?: number;
  tone?: AttentionTone;
}

export function AttentionDot({ entry, collapsed, count = 1, tone = "warning" }: Props) {
  const { t } = useTranslation();
  return (
    <span
      role="img"
      data-testid={`nav-dot-${entry.replace(/\//g, "")}`}
      data-tone={tone}
      aria-label={t("nav.needsAttention")}
      className={cn(
        "shrink-0 rounded-full",
        tone === "danger" ? "bg-danger text-on-status" : "bg-warning text-warning-foreground",
        collapsed
          ? "absolute right-[5px] top-[5px] size-[7px] ring-2 ring-surface-sidebar"
          : "ml-auto inline-flex h-4 min-w-4 items-center justify-center px-1 text-2xs font-heavy leading-none",
      )}
    >
      {collapsed ? null : count}
    </span>
  );
}
