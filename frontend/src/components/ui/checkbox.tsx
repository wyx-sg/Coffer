// src/components/ui/checkbox.tsx
// A 15px checkbox (Foundations · Selection): a styled native <input type="checkbox">
// (implicit role="checkbox", full keyboard support) that also drives the
// `indeterminate` DOM property — needed for a "some rows selected" select-all.
// The box is the input itself (`appearance-none`); the check / dash marks are
// icons layered over it and shown by the input's own :checked / :indeterminate
// state, so they can never disagree with what assistive tech reads.
import { useEffect, useRef, type InputHTMLAttributes } from "react";
import { Check, Minus } from "lucide-react";

import { cn } from "@/lib/utils";

interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  indeterminate?: boolean;
}

const MARK =
  "pointer-events-none absolute left-1/2 top-1/2 hidden size-[11px] -translate-x-1/2 -translate-y-1/2 stroke-[3] text-accent-foreground peer-disabled:opacity-disabled";

/** `className` lands on the wrapper, so layout classes (margins, alignment)
 *  place the whole control. */
export function Checkbox({ className, indeterminate, ...props }: CheckboxProps) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate ?? false;
  }, [indeterminate]);
  return (
    <span className={cn("relative inline-flex size-[15px] shrink-0 align-middle", className)}>
      <input
        ref={ref}
        type="checkbox"
        className={cn(
          "peer m-0 size-[15px] cursor-pointer appearance-none rounded-xs border border-border bg-surface-raised",
          "transition-colors duration-fast ease-standard",
          "checked:border-accent checked:bg-accent indeterminate:border-accent indeterminate:bg-accent",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
          "disabled:cursor-default disabled:opacity-disabled",
        )}
        {...props}
      />
      <Check aria-hidden className={cn(MARK, "peer-checked:block peer-indeterminate:hidden")} />
      <Minus aria-hidden className={cn(MARK, "peer-indeterminate:block")} />
    </span>
  );
}
