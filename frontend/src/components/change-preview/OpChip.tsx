// src/components/change-preview/OpChip.tsx
// The operation chip of a change: + Add, ~ Modify or − Remove, h20 (h18 inside a target row).
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import type { ChangeOp } from "@/lib/changePreview/changeCounts";

const LOOK: Record<ChangeOp, { symbol: string; tone: string }> = {
  add: { symbol: "+", tone: "bg-success-soft text-success" },
  modify: { symbol: "~", tone: "bg-chip text-text-muted" },
  remove: { symbol: "−", tone: "bg-danger-soft text-danger" },
};

interface Props {
  op: ChangeOp;
  /** `sm` is the 18px chip of a target row; `md` (20px) everywhere else. */
  size?: "sm" | "md";
  className?: string;
}

export function OpChip({ op, size = "md", className }: Props) {
  const { t } = useTranslation();
  const look = LOOK[op];
  return (
    <span
      data-op={op}
      className={cn(
        "inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-sm px-1.5 text-2xs font-label",
        size === "sm" ? "h-[18px]" : "h-5",
        look.tone,
        className,
      )}
    >
      <span aria-hidden className="font-mono font-medium">
        {look.symbol}
      </span>
      {t(`changePreview.op.${op}`)}
    </span>
  );
}
