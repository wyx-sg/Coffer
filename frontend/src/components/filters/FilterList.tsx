// src/components/filters/FilterList.tsx — the option list inside a FilterPill's popover.
import type { KeyboardEvent, RefObject } from "react";
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import type { FilterSection } from "./filterSections";

const ROW = "flex h-7 w-full items-center gap-2 rounded-sm px-2 text-left text-xs text-text";

function Box({ checked }: { checked: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-[14px] shrink-0 items-center justify-center rounded-[4px]",
        checked ? "bg-accent text-accent-foreground" : "border border-input bg-surface-raised",
      )}
    >
      {checked ? <Check className="size-2.5" strokeWidth={3} /> : null}
    </span>
  );
}

function Radio({ checked }: { checked: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-[14px] shrink-0 items-center justify-center rounded-full border",
        checked ? "border-accent" : "border-input bg-surface-raised",
      )}
    >
      {checked ? <span className="size-2 rounded-full bg-accent" /> : null}
    </span>
  );
}

interface Props {
  label: string;
  single: boolean;
  selected: readonly string[];
  sections: readonly FilterSection[];
  rowCount: number;
  listRef: RefObject<HTMLDivElement>;
  onKeyDown: (e: KeyboardEvent) => void;
  onToggle: (value: string) => void;
  onOnly: (value: string) => void;
}

export function FilterList({
  label,
  single,
  selected,
  sections,
  rowCount,
  listRef,
  onKeyDown,
  onToggle,
  onOnly,
}: Props) {
  const { t } = useTranslation();
  return (
    <div
      ref={listRef}
      role="listbox"
      aria-label={label}
      aria-multiselectable={!single}
      onKeyDown={onKeyDown}
      className="flex max-h-[168px] flex-col overflow-y-auto"
    >
      {sections.map((section, si) => (
        <div
          key={section.id || si}
          className={cn(si > 0 && "mt-1 border-t border-border-subtle pt-1")}
        >
          {section.label ? (
            <div className="px-2 pb-0.5 pt-1 text-2xs font-semibold text-text-subtle">
              {section.label}
            </div>
          ) : null}
          {section.rows.map((o) => {
            const checked = selected.includes(o.value);
            return (
              <div key={o.value} className="group relative">
                <button
                  type="button"
                  role="option"
                  aria-selected={checked}
                  onClick={() => onToggle(o.value)}
                  className={cn(
                    ROW,
                    "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none",
                  )}
                >
                  {single ? <Radio checked={checked} /> : <Box checked={checked} />}
                  <span className="min-w-0 flex-1 truncate">{o.label}</span>
                </button>
                {single ? null : (
                  <button
                    type="button"
                    onClick={() => onOnly(o.value)}
                    aria-label={`${t("filters.only")}: ${o.label}`}
                    className="absolute right-1.5 top-1/2 hidden -translate-y-1/2 rounded-sm px-1 text-xs text-accent-text hover:underline focus-visible:block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring group-focus-within:block group-hover:block"
                  >
                    {t("filters.only")}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      ))}
      {rowCount === 0 ? (
        <p className="px-2 py-3 text-center text-xs text-text-subtle">{t("filters.noMatches")}</p>
      ) : null}
    </div>
  );
}
