// src/components/custom-tools/GroupBanner.tsx — one tinted banner under a group's header (4.2.21–4.2.23): an
// icon, a 13/550 title, a 12px body and the buttons that fix the problem it states.
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type BannerTint = "err" | "warn" | "off";

const TINT: Record<BannerTint, { box: string; icon: string }> = {
  err: { box: "bg-danger-soft", icon: "text-danger" },
  warn: { box: "bg-warning-soft", icon: "text-warning" },
  off: { box: "bg-surface-sunken", icon: "text-text-muted" },
};

interface Props {
  tint: BannerTint;
  icon: LucideIcon;
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  testId: string;
}

export function GroupBanner({ tint, icon: Icon, title, children, actions, testId }: Props) {
  return (
    <div
      role="status"
      data-testid={testId}
      className={cn("flex items-start gap-2.5 rounded-lg px-3 py-2.5", TINT[tint].box)}
    >
      <Icon
        className={cn("mt-px size-[15px] shrink-0", TINT[tint].icon)}
        strokeWidth={1.75}
        aria-hidden
      />
      <div className="flex min-w-0 flex-1 flex-col gap-[3px]">
        <p className="text-sm font-label text-text">{title}</p>
        {children ? <p className="text-xs leading-[1.45] text-text-muted">{children}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}
