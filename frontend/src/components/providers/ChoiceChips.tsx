// src/components/providers/ChoiceChips.tsx — a row of single-choice chips (the Add dialog's vendor picker).
import { cn } from "@/lib/utils";

interface Props<T extends string> {
  label: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}

export function ChoiceChips<T extends string>({ label, value, options, onChange }: Props<T>) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            "h-7 rounded-md border px-2.5 text-xs font-label outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
            o.value === value
              ? "border-accent bg-accent-soft text-accent-text"
              : "border-border bg-surface-raised text-text hover:bg-surface-hover",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
