// src/components/agents/tabs/OwnerFilterControl.tsx — All · Coffer's · The agent's own, as one segmented radio group.
import { useRef } from "react";
import { useTranslation } from "react-i18next";

import { OWNER_FILTERS, type OwnerFilter } from "@/lib/agents/owner";
import { cn } from "@/lib/utils";

interface Props {
  value: OwnerFilter;
  onChange: (next: OwnerFilter) => void;
}

export function OwnerFilterControl({ value, onChange }: Props) {
  const { t } = useTranslation();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  // Arrow keys move the choice, as in any radio group.
  const onKeyDown = (event: React.KeyboardEvent, index: number) => {
    const step =
      event.key === "ArrowRight" || event.key === "ArrowDown"
        ? 1
        : event.key === "ArrowLeft" || event.key === "ArrowUp"
          ? -1
          : 0;
    if (step === 0) return;
    event.preventDefault();
    const next = (index + step + OWNER_FILTERS.length) % OWNER_FILTERS.length;
    onChange(OWNER_FILTERS[next]);
    refs.current[next]?.focus();
  };

  return (
    <div
      role="radiogroup"
      aria-label={t("agents.kindTab.owner.label")}
      className="inline-flex gap-0.5 rounded-md border border-border-subtle bg-surface-sunken p-[3px]"
    >
      {OWNER_FILTERS.map((filter, index) => {
        const checked = filter === value;
        return (
          <button
            key={filter}
            ref={(el) => {
              refs.current[index] = el;
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            onClick={() => onChange(filter)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={cn(
              "h-6 rounded-sm px-2.5 text-xs font-label outline-none transition-colors duration-fast focus-visible:ring-2 focus-visible:ring-focus-ring",
              checked
                ? "bg-surface-raised text-text shadow-lifted"
                : "text-text-muted hover:text-text",
            )}
          >
            {t(`agents.kindTab.owner.${filter}`)}
          </button>
        );
      })}
    </div>
  );
}
