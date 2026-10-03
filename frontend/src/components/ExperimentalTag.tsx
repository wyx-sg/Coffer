// src/components/ExperimentalTag.tsx — the one "Experimental" mark (Foundations 0.7.05).
//
// Marked once: beside a page's title (PageHeader's `experimental` prop) and in
// Settings › Features — never on a sidebar row. It is not a status and not the
// accent, so it carries no colour, icon or dot: 16 high, 1px border, r4, 11px muted.
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

export function ExperimentalTag({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <span
      className={cn(
        "inline-flex h-4 shrink-0 items-center rounded-[4px] border border-border px-1 text-[11px] font-normal leading-none text-text-muted",
        className,
      )}
    >
      {t("common.experimental")}
    </span>
  );
}
