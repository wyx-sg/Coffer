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
      <div className="space-y-1">
        {back ? (
          <Link
            to={back.to}
            className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="size-4" aria-hidden />
            {back.label}
          </Link>
        ) : null}
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="flex items-center gap-3 text-3xl tracking-tight">
            {Icon ? <Icon className="size-7 text-primary" strokeWidth={1.5} aria-hidden /> : null}
            {title}
          </h1>
          {badges}
        </div>
        {subtitle ? <p className="max-w-prose text-sm text-muted-foreground">{subtitle}</p> : null}
      </div>
      {actions}
    </header>
  );
}
