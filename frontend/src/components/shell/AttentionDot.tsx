// src/components/shell/AttentionDot.tsx — the count badge a sidebar entry carries while its kind needs the user.
//
// Expanded, a pill with the count in the danger-strong tone, capped at "9+"
// (board 1.1.01), 10px / 700. On the collapsed rail the words are gone, so it
// shrinks to a 7px dot of the same colour riding the icon's corner (3px from
// the top, 4px from the right, a 2px ring of the sidebar colour), and the
// row's tooltip carries the count (board 1.1.01). The accessible name says
// the entry needs attention; the count itself is the visible text.
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

/** The most the pill spells out; anything above reads "9+". */
const MAX_SHOWN = 9;

interface Props {
  /** The entry's route, for the test id (`nav-dot-sync`). */
  entry: string;
  collapsed: boolean;
  /** How many things need the user; the rail shows a dot either way. */
  count?: number;
}

export function AttentionDot({ entry, collapsed, count = 1 }: Props) {
  const { t } = useTranslation();
  return (
    <span
      role="img"
      data-testid={`nav-dot-${entry.replace(/\//g, "")}`}
      aria-label={t("nav.needsAttention")}
      className={cn(
        "shrink-0 rounded-full bg-danger-strong text-on-status",
        collapsed
          ? "absolute right-1 top-[3px] size-[7px] ring-2 ring-surface-sidebar"
          : "ml-auto inline-flex h-4 min-w-4 items-center justify-center px-1 text-3xs font-heavy leading-none",
      )}
    >
      {collapsed ? null : count > MAX_SHOWN ? `${MAX_SHOWN}+` : count}
    </span>
  );
}
