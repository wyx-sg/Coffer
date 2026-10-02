// src/components/status/StatusWord.tsx — a status as a dot beside its word, for list rows and the sidebar footer.
//
// Healthy reads quietly: an ok or off word is muted text, while a warn or err
// word takes its status colour (Foundations-Status "Status · dot + word").
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { toneTextClass } from "@/lib/statusColors";
import { StatusDot } from "./StatusDot";
import { STATUS_TONE, type StatusTone } from "@/lib/statusTone";

interface StatusWordProps {
  tone: StatusTone;
  /** The word the dot means — Running, Degraded, Failing, Disabled… */
  children: ReactNode;
  className?: string;
}

export function StatusWord({ tone, children, className }: StatusWordProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-[7px] whitespace-nowrap text-xs font-normal",
        toneTextClass(STATUS_TONE[tone]),
        className,
      )}
    >
      <StatusDot tone={tone} />
      {children}
    </span>
  );
}
