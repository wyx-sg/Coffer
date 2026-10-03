// src/components/filters/TimeRangeParts.tsx — pieces of the TimeRangePill popover: the preset list, the HH:MM field, the draft reader.
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import type { TimeRangePreset } from "./TimeRangePill";

export const FIELD =
  "flex h-7 w-full items-center rounded-md border border-border bg-surface-raised px-2 text-xs text-text";

const OPTION =
  "flex h-7 items-center gap-2 rounded-sm px-2 text-left text-xs text-text hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none";

export function TimeField({
  value,
  onChange,
  invalid,
  placeholder,
  name,
}: {
  value: string;
  onChange: (v: string) => void;
  invalid: boolean;
  placeholder: string;
  name: string;
}) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value.trim())}
      placeholder={placeholder}
      aria-label={name}
      aria-invalid={invalid || undefined}
      inputMode="numeric"
      maxLength={5}
      className={cn(
        "h-7 w-[76px] rounded-md border bg-surface-raised px-2 text-xs text-text outline-none placeholder:text-text-subtle focus:ring-2 focus:ring-focus-ring",
        invalid ? "border-danger" : "border-border",
      )}
    />
  );
}

export function PresetList({
  label,
  presets,
  value,
  custom,
  onChoose,
  onCustom,
}: {
  label: string;
  presets: readonly TimeRangePreset[];
  value: string;
  custom: boolean;
  onChoose: (id: string) => void;
  onCustom: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div role="listbox" aria-label={label} className="flex flex-col">
      {presets.map((p) => {
        const selected = !custom && p.id === value;
        return (
          <button
            key={p.id}
            type="button"
            role="option"
            aria-selected={selected}
            onClick={() => onChoose(p.id)}
            className={cn(OPTION, selected && "bg-surface-selected")}
          >
            <span className="flex-1">{p.label}</span>
            {selected ? <Check className="size-3.5 text-accent-text" aria-hidden /> : null}
          </button>
        );
      })}
      <button
        type="button"
        role="option"
        aria-selected={custom}
        onClick={onCustom}
        className={cn(OPTION, custom && "bg-surface-selected")}
      >
        <span className="flex-1">{t("filters.timeRange.custom")}</span>
        {custom ? <Check className="size-3.5 text-accent-text" aria-hidden /> : null}
      </button>
    </div>
  );
}
