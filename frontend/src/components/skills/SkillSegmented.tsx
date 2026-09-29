// frontend/src/components/skills/SkillSegmented.tsx
// The small segmented control the Skills page uses twice — the library's
// All / On / Off filter and a Markdown file's Preview / Source switch: a sunken
// track of toggle buttons, the pressed one lifted (Foundations "Segmented").
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
  className?: string;
}

export function SkillSegmented<T extends string>({
  value,
  options,
  onChange,
  label,
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
            onClick={() => onChange(o.value)}
            className={cn(
              "h-6 whitespace-nowrap rounded-sm px-2.5 text-xs font-label transition-colors duration-fast",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
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
