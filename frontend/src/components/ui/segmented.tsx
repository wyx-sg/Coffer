// src/components/ui/segmented.tsx — the Foundations "Segmented" control: a sunken track of toggle buttons, the pressed one lifted.
import { cn } from "@/lib/utils";

interface Option<T extends string> {
  value: T;
  label: string;
}

interface Props<T extends string> {
  value: T;
  options: readonly Option<T>[];
  onChange: (value: T) => void;
  /** The group's accessible name. */
  label: string;
  disabled?: boolean;
  className?: string;
}

/** A small set of mutually exclusive choices shown at once (Light / Dark / System). */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  disabled,
  className,
}: Props<T>) {
  return (
    <div
      role="group"
      aria-label={label}
      className={cn(
        "inline-flex shrink-0 gap-0.5 rounded-md border border-border-subtle bg-surface-sunken p-0.5",
        className,
      )}
    >
      {options.map((o) => {
        const pressed = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={pressed}
            disabled={disabled}
            onClick={() => onChange(o.value)}
            className={cn(
              "h-6 whitespace-nowrap rounded-sm px-2.5 text-xs font-label transition-colors duration-fast",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring disabled:opacity-50",
              pressed
                ? "bg-surface-raised text-text shadow-lifted"
                : "text-text-muted hover:text-text",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
