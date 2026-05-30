// frontend/src/components/PageHeader.tsx
//
// The one page header for every top-level surface (Agents, MCP servers,
// Audit log, Settings): an icon + title on the left, optional subtitle
// beneath, and optional actions (buttons) on the right. Keeps page chrome
// visually uniform across the app.
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function PageHeader({
  icon: Icon,
  title,
  subtitle,
  actions,
}: {
  icon: LucideIcon;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-1">
        <h1 className="flex items-center gap-3 text-3xl tracking-tight">
          <Icon className="size-7 text-primary" strokeWidth={1.5} aria-hidden />
          {title}
        </h1>
        {subtitle ? <p className="max-w-prose text-sm text-muted-foreground">{subtitle}</p> : null}
      </div>
      {actions}
    </header>
  );
}
