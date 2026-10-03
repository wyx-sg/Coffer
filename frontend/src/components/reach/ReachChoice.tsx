// src/components/reach/ReachChoice.tsx — one mode row of ReachControl's panel: a 16px radio, a title and its sub line.
//
// Foundations-Reach "Modes": radio · title 13/550 · sub 12 muted. The radio is
// the native input restyled (`appearance-none`), so its checked state is the
// one assistive tech reads; the 6px on-accent dot is layered over it by the
// input's own :checked. It is NAMED by the title alone (aria-labelledby) and
// DESCRIBED by the sub line, so "Off" is still found as /^off$/.
//
// `onClick`, not `onChange`: re-picking the live choice is a real gesture (it
// is how a user confirms and closes) and an already-checked radio fires no
// change. Keyboard activation clicks too, so nothing is lost; `readOnly` only
// tells React the missing `onChange` is meant.
import { useId } from "react";

import { cn } from "@/lib/utils";

interface Props {
  /** Radio group name — per ReachControl instance, never shared. */
  group: string;
  checked: boolean;
  disabled: boolean;
  text: string;
  sub: string;
  onPick: () => void;
}

export function ReachChoice({ group, checked, disabled, text, sub, onPick }: Props) {
  const id = useId();
  // Two labels for one input: the first holds the radio and its title (and is
  // the row's `closest("label")`), the second is the sub line, which still
  // picks the choice when clicked.
  return (
    <div className="grid grid-cols-[16px_1fr] gap-x-2.5 py-[3px]">
      <label className="col-span-2 flex cursor-pointer items-center gap-2.5">
        <span className="relative inline-flex size-4 shrink-0">
          <input
            id={`${id}-input`}
            type="radio"
            name={group}
            aria-labelledby={`${id}-title`}
            aria-describedby={`${id}-sub`}
            className={cn(
              "peer m-0 size-4 cursor-pointer appearance-none rounded-full border border-border bg-surface-raised",
              "transition-colors duration-fast ease-standard checked:border-accent checked:bg-accent",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
              "disabled:cursor-default disabled:opacity-disabled",
            )}
            checked={checked}
            disabled={disabled}
            readOnly
            onClick={onPick}
          />
          <span
            aria-hidden
            className="pointer-events-none absolute left-1/2 top-1/2 hidden size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent-foreground peer-checked:block"
          />
        </span>
        <span id={`${id}-title`} className="text-sm font-label text-text">
          {text}
        </span>
      </label>
      <label
        id={`${id}-sub`}
        htmlFor={`${id}-input`}
        className="col-start-2 cursor-pointer text-xs text-text-muted"
      >
        {sub}
      </label>
    </div>
  );
}
