// src/components/mcp/server/McpCallout.tsx — one tinted callout on the open server's Overview: an icon, a title, a body and one action (design 4.1.01–4.1.06).
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type CalloutTint = "ok" | "err" | "warn" | "off" | "info";

const TINT: Record<CalloutTint, { box: string; icon: string }> = {
  ok: { box: "bg-success-soft", icon: "text-success" },
  err: { box: "bg-danger-soft", icon: "text-danger" },
  warn: { box: "bg-warning-soft", icon: "text-warning" },
  off: { box: "bg-surface-sunken", icon: "text-text-muted" },
  // Tiering is information, not a status: the accent's soft fill.
  info: { box: "bg-accent-soft", icon: "text-accent-text" },
};

interface Props {
  tint: CalloutTint;
  icon: LucideIcon;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  testId: string;
}

export function McpCallout({ tint, icon: Icon, title, children, action, testId }: Props) {
  return (
    <div
      role="status"
      data-testid={testId}
      className={cn("flex items-start gap-3 rounded-xl px-4 py-3", TINT[tint].box)}
    >
      <Icon className={cn("mt-0.5 size-4 shrink-0", TINT[tint].icon)} strokeWidth={2} aria-hidden />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="text-sm font-semibold text-text">{title}</p>
        {children ? <div className="text-xs leading-relaxed text-text">{children}</div> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
