// src/components/shell/AttentionDot.tsx — the one dot a sidebar entry carries while its kind needs attention.
//
// A dot, not a count: what is waiting is one situation to look at, and a
// number would be the times a timer re-raised it. On the collapsed rail it
// rides the icon, which is all there is.
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

interface Props {
  /** The entry's route, for the test id (`nav-dot-sync`). */
  entry: string;
  collapsed: boolean;
}

export function AttentionDot({ entry, collapsed }: Props) {
  const { t } = useTranslation();
  return (
    <span
      role="img"
      data-testid={`nav-dot-${entry.replace(/\//g, "")}`}
      aria-label={t("nav.needsAttention")}
      className={cn(
        "size-1.5 shrink-0 rounded-full bg-danger",
        collapsed ? "absolute right-1.5 top-1.5" : null,
      )}
    />
  );
}
