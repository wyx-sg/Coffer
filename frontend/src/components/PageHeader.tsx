// src/components/PageHeader.tsx — the one page header for every surface.
//
// Icon + title on the left (with optional badges beside the title and an
// optional "← back" link above it for detail pages), optional subtitle
// beneath, and optional actions (buttons) on the right. Keeps page chrome
// visually uniform across the app.
import type { LucideIcon } from "lucide-react";
import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { cn } from "@/lib/utils";

interface Props {
  /** Optional — list pages carry their kind icon; detail pages usually omit it. */
  icon?: LucideIcon;
  title: ReactNode;
  subtitle?: ReactNode;
  /** Right-aligned slot for the page's primary buttons. */
  actions?: ReactNode;
  /** Inline slot beside the title — status pills, kind chips. */
  badges?: ReactNode;
  /** Detail pages: a "← label" link back to the list, rendered above the title. */
  back?: { to: string; label: string };
}

export function PageHeader({ icon: Icon, title, subtitle, actions, badges, back }: Props) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-1.5">
        {back ? (
          <Link
            to={back.to}
            className="inline-flex items-center gap-1 text-xs text-text-subtle transition-colors duration-fast hover:text-text"
          >
            <ArrowLeft className="size-3.5" aria-hidden />
            {back.label}
          </Link>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          {/* Page title 18/650; a detail page (it has a back link) 20/650. */}
          <h1
            className={cn(
              "flex min-h-control-md items-center gap-2.5 font-bold tracking-[-0.01em]",
              back ? "text-xl" : "text-lg",
            )}
          >
            {Icon ? (
              <Icon className="size-5 text-text-subtle" strokeWidth={1.75} aria-hidden />
            ) : null}
            {title}
          </h1>
          {badges}
        </div>
        {subtitle ? <p className="max-w-prose text-sm text-text-subtle">{subtitle}</p> : null}
      </div>
      {actions}
    </header>
  );
}
