// src/components/ui/spinner.tsx
// The inline spinner (Foundations-Feedback): a 14px, stroke-2 ring turning every 700ms.
//
// It says "working on it" beside a word ("Checking github…") or in a button
// that is waiting (Button `loading`). A list that is loading uses Skeleton
// rows instead. `delayed` holds it invisible for the first 300ms, so an answer
// that comes back quickly never flashes a spinner. Under reduced motion it
// stands still.
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

interface SpinnerProps {
  /** Wait 300ms before showing (inline status lines); a button shows at once. */
  delayed?: boolean;
  /** Names it for assistive tech (`role="status"`); omit when a word beside it
   *  already says what is happening. */
  label?: string;
  className?: string;
}

export function Spinner({ delayed = false, label, className }: SpinnerProps) {
  return (
    <Loader2
      role={label ? "status" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      data-spinner=""
      className={cn(
        "size-3.5 shrink-0 stroke-2",
        // Reduced motion: the plain spinner stops; the delayed one keeps its
        // show step (index.css caps it to one short run, so it still appears).
        delayed ? "animate-spinner-delayed opacity-0" : "animate-spinner motion-reduce:animate-none",
        className,
      )}
    />
  );
}
