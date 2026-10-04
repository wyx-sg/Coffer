// src/components/providers/ModelsToolbar.tsx — the Models section's filter row: search, and Type as a filter pill.
import { useState, type ReactNode } from "react";
import { Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { pillClass } from "@/components/filters/pillStyles";
import { SearchInput } from "@/components/SearchInput";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { Modality } from "@/lib/api/providers";
import { cn } from "@/lib/utils";

interface Props {
  query: string;
  onQuery: (q: string) => void;
  types: readonly Modality[];
  type: Modality | "all";
  onType: (t: Modality | "all") => void;
  /** Right-aligned text on the same row (the Add dialog's "7 of 42 selected"). */
  trailing?: ReactNode;
  /** Right-aligned controls on the same row (Turn all on / off). */
  actions?: ReactNode;
  /** Width of the search field. */
  searchClass?: string;
}

export function ModelsToolbar({
  query,
  onQuery,
  types,
  type,
  onType,
  trailing,
  actions,
  searchClass = "w-60",
}: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rows = [
    { value: "all" as const, label: t("providers.models.allTypes") },
    ...types.map((m) => ({ value: m, label: t(`providers.modalities.${m}`) })),
  ];
  const chosen = type !== "all" ? rows.find((r) => r.value === type) : undefined;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <SearchInput
        value={query}
        onChange={onQuery}
        placeholder={t("providers.models.search")}
        ariaLabel={t("providers.models.search")}
        className={searchClass}
      />
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button type="button" className={cn(pillClass(!!chosen, open), "px-2.5")}>
            <span className={cn(chosen && "text-text-muted")}>
              {chosen ? `${t("providers.models.typeFilter")}:` : t("providers.models.typeFilter")}
            </span>
            {chosen ? <span className="font-label text-text">{chosen.label}</span> : null}
            <ChevronDown className="size-3.5 text-text-subtle" aria-hidden />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-48 p-1" align="start">
          <div role="listbox" aria-label={t("providers.models.typeFilter")}>
            {rows.map((r) => (
              <button
                key={r.value}
                type="button"
                role="option"
                aria-selected={r.value === type}
                onClick={() => {
                  onType(r.value);
                  setOpen(false);
                }}
                className={cn(
                  "flex h-7 w-full items-center gap-2 rounded-sm px-2 text-left text-sm text-text",
                  "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none",
                  r.value === type && "bg-surface-selected font-label",
                )}
              >
                <span className="min-w-0 flex-1 truncate">{r.label}</span>
                {r.value === type ? (
                  <Check className="size-3.5 text-accent-text" aria-hidden />
                ) : null}
              </button>
            ))}
          </div>
        </PopoverContent>
      </Popover>
      {actions ? <div className="ml-auto flex items-center gap-1.5">{actions}</div> : null}
      {trailing ? <span className="ml-auto text-xs text-text-muted">{trailing}</span> : null}
    </div>
  );
}
