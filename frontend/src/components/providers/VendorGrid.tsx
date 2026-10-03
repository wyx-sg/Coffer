// src/components/providers/VendorGrid.tsx — the Add dialog's vendor picker: a 4 × 2 grid of equal buttons, each with its 16px mark.
import { cn } from "@/lib/utils";
import type { PresetId } from "@/lib/providers/presets";
import { VendorIcon } from "./VendorIcon";

interface Props {
  label: string;
  value: PresetId;
  options: readonly { value: PresetId; label: string }[];
  onChange: (value: PresetId) => void;
}

export function VendorGrid({ label, value, options, onChange }: Props) {
  return (
    <div role="radiogroup" aria-label={label} className="grid grid-cols-4 gap-1.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            "flex h-7 min-w-0 items-center justify-center gap-1.5 rounded-md border px-2 text-xs font-label outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
            o.value === value
              ? "border-accent bg-accent-soft text-accent-text"
              : "border-border bg-surface-raised text-text hover:bg-surface-hover",
          )}
        >
          <VendorIcon id={o.value} />
          <span className="truncate">{o.label}</span>
        </button>
      ))}
    </div>
  );
}
