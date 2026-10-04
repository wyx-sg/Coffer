// src/components/status/StatusPill.tsx — the filled status pill a detail header carries.
//
// 22 high, 8 across, radius 6; a 6px dot 6 from a 12/600 word on the tone's
// soft fill with the status colour as text — off is a neutral fill with muted
// text (Foundations-Status "Status pill"). Detail headers only; rows use
// StatusWord.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { toneClass } from "@/lib/statusColors";
import { StatusDot } from "./StatusDot";
import { STATUS_TONE, type StatusTone } from "@/lib/statusTone";

interface StatusPillProps {
  tone: StatusTone;
  children: ReactNode;
  className?: string;
}

export function StatusPill({ tone, children, className }: StatusPillProps) {
  return (
    <span
      className={cn(
        "inline-flex h-[22px] items-center gap-1.5 whitespace-nowrap rounded-item px-2 text-xs font-semibold",
        toneClass(STATUS_TONE[tone]),
        className,
      )}
    >
      <StatusDot tone={tone} size={6} />
      {children}
    </span>
  );
}
