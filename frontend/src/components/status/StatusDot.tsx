// src/components/status/StatusDot.tsx — the round status mark that always sits beside its word.
//
// Four tones only (Foundations-Status): ok, warn, err and off. The dot carries
// the status colour; it is decorative, because the word next to it says the
// same thing — a status is never colour alone (Foundations-Principles "Status
// is dot + word").
import { cn } from "@/lib/utils";
import { toneDotClass } from "@/lib/statusColors";
import { STATUS_TONE, type StatusTone } from "./statusTone";

interface StatusDotProps {
  tone: StatusTone;
  /** Diameter in px: 7 beside a word, 6 inside a pill. */
  size?: 6 | 7;
  className?: string;
}

export function StatusDot({ tone, size = 7, className }: StatusDotProps) {
  return (
    <span
      aria-hidden
      data-tone={tone}
      className={cn(
        "inline-block shrink-0 rounded-full",
        size === 6 ? "size-1.5" : "size-[7px]",
        toneDotClass(STATUS_TONE[tone]),
        className,
      )}
    />
  );
}
