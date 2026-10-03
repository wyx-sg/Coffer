// src/components/LongList.tsx — "Long" lists (principle 21, Foundations 0.6.01): five rows, then "Showing 5 of N · Show all".
//
// The `useLongList` hook (useLongList.ts) holds the state. Show all expands in place. Inside a dialog the expanded list scrolls within
// itself (`scrollInside`) so the dialog keeps its height.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ShowAllRowProps {
  shown: number;
  total: number;
  onShowAll: () => void;
  className?: string;
}

/** The footer row under a collapsed long list; render it only while `collapsed`. */
export function ShowAllRow({ shown, total, onShowAll, className }: ShowAllRowProps) {
  const { t } = useTranslation();
  return (
    <div
      className={cn(
        "flex min-h-9 items-center gap-1.5 border-t border-border-subtle px-3 text-xs text-text-muted",
        className,
      )}
    >
      <span>{t("common.longList.showing", { shown, total })}</span>
      <span aria-hidden>·</span>
      <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={onShowAll}>
        {t("common.longList.showAll")}
      </Button>
    </div>
  );
}
