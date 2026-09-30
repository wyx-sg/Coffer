// frontend/src/components/skills/SkillChoiceCards.tsx
// The radio cards every "confirmed choices" dialog of the Skills page opens
// with (canvas 4.3.19, 4.3.23, 4.3.24, 4.3.27, 4.3.41): Keep my edits / Take
// the update / Merge with an agent, Restore from master / Adopt the agent's version,
// Replace it with Coffer's link / Adopt this folder. Nothing is chosen for the
// reader unless the caller passes a value; the chosen card is the lifted one.
import { cn } from "@/lib/utils";

interface SkillChoice<T extends string> {
  value: T;
  title: string;
  help: string;
  /** Shown but not choosable, with the reason in its help line. */
  disabled?: boolean;
}

interface Props<T extends string> {
  /** The group's accessible name. */
  label: string;
  choices: readonly SkillChoice<T>[];
  value: T | null;
  onChange: (value: T) => void;
}

export function SkillChoiceCards<T extends string>({ label, choices, value, onChange }: Props<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn("grid gap-2.5", choices.length === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2")}
    >
      {choices.map((c) => {
        const on = c.value === value;
        return (
          <button
            key={c.value}
            type="button"
            role="radio"
            aria-checked={on}
            disabled={c.disabled}
            onClick={() => onChange(c.value)}
            className={cn(
              "flex items-start gap-2.5 rounded-lg border px-3.5 py-3 text-left transition-colors duration-fast",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
              "disabled:cursor-not-allowed disabled:opacity-disabled",
              on
                ? "border-accent bg-accent-soft"
                : "border-border bg-surface-raised hover:bg-surface-hover",
            )}
          >
            <span
              aria-hidden
              className={cn(
                "mt-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded-full border",
                on ? "border-accent" : "border-border",
              )}
            >
              {on ? <span className="size-2 rounded-full bg-accent" /> : null}
            </span>
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="text-sm font-label text-text">{c.title}</span>
              <span className="text-xs leading-[1.45] text-text-muted">{c.help}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
