// src/components/preview/FindWidget.tsx
// The unified in-preview find bar — a small floating box pinned to the top-right
// of any preview. Presentational and fully controlled by useFind(); the same
// widget serves code/text (CodeMirror) and rendered Markdown previews so the
// find UX is identical across Coffer. Read-only previews never replace, so this
// is find-only (no replace field).
import { forwardRef } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowUp, CaseSensitive, X } from "lucide-react";

import { cn } from "@/lib/utils";

interface FindWidgetProps {
  query: string;
  count: number;
  /** 0-based active match index, or -1 when there are none. */
  active: number;
  caseSensitive: boolean;
  onQueryChange: (value: string) => void;
  onToggleCase: () => void;
  onNext: () => void;
  onPrev: () => void;
  onClose: () => void;
  className?: string;
}

export const FindWidget = forwardRef<HTMLInputElement, FindWidgetProps>(function FindWidget(
  {
    query,
    count,
    active,
    caseSensitive,
    onQueryChange,
    onToggleCase,
    onNext,
    onPrev,
    onClose,
    className,
  },
  ref,
) {
  const { t } = useTranslation();

  const status =
    query === ""
      ? ""
      : count === 0
        ? t("preview.find.noMatches")
        : t("preview.find.matches", { active: active + 1, total: count });

  return (
    <div
      className={cn(
        "absolute right-2 top-2 z-10 flex items-center gap-1 rounded-md border border-border bg-card p-1 shadow-md",
        className,
      )}
      role="search"
    >
      <input
        ref={ref}
        type="text"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            if (e.shiftKey) onPrev();
            else onNext();
          } else if (e.key === "Escape") {
            e.preventDefault();
            onClose();
          }
        }}
        placeholder={t("preview.find.placeholder")}
        aria-label={t("preview.find.label")}
        className="h-7 w-40 rounded-sm bg-transparent px-2 text-xs text-foreground outline-none placeholder:text-muted-foreground"
      />
      <span className="min-w-[3.5rem] px-1 text-center text-xs tabular-nums text-muted-foreground">
        {status}
      </span>
      <button
        type="button"
        onClick={onToggleCase}
        aria-label={t("preview.find.caseSensitive")}
        aria-pressed={caseSensitive}
        className={cn(
          "flex size-7 items-center justify-center rounded-sm hover:bg-muted",
          caseSensitive ? "bg-muted text-foreground" : "text-muted-foreground",
        )}
      >
        <CaseSensitive className="size-4" />
      </button>
      <button
        type="button"
        onClick={onPrev}
        disabled={count === 0}
        aria-label={t("preview.find.prev")}
        className="flex size-7 items-center justify-center rounded-sm text-muted-foreground hover:bg-muted disabled:opacity-40 disabled:hover:bg-transparent"
      >
        <ArrowUp className="size-4" />
      </button>
      <button
        type="button"
        onClick={onNext}
        disabled={count === 0}
        aria-label={t("preview.find.next")}
        className="flex size-7 items-center justify-center rounded-sm text-muted-foreground hover:bg-muted disabled:opacity-40 disabled:hover:bg-transparent"
      >
        <ArrowDown className="size-4" />
      </button>
      <button
        type="button"
        onClick={onClose}
        aria-label={t("preview.find.close")}
        className="flex size-7 items-center justify-center rounded-sm text-muted-foreground hover:bg-muted"
      >
        <X className="size-4" />
      </button>
    </div>
  );
});
