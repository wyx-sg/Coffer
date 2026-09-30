// src/components/PageHeader.tsx — the one page header for every surface.
//
// The boards draw one header (1.2 App shell, every list and detail board): an
// optional "← list" link above, then one row — the title (18/650), anything
// that sits beside it (a count, a status, "Unsaved changes"), and the page's
// actions pushed to the right — and an optional subtitle under the row. Detail
// pages keep one fixed action order: reach → test/refresh → edit → delete.
import type { LucideIcon } from "lucide-react";
import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

interface Props {
  /** Accepted for compatibility; the boards draw no icon beside a page title,
   *  so it is not rendered (the sidebar entry already carries it). */
  icon?: LucideIcon;
  title: ReactNode;
  subtitle?: ReactNode;
  /** Right-aligned slot for the page's primary buttons, on the title's row. */
  actions?: ReactNode;
  /** Inline slot beside the title — a count, a status, a kind chip. */
  badges?: ReactNode;
  /** Detail pages: a "← label" link back to the list, rendered above the title. */
  back?: { to: string; label: string };
}

export function PageHeader({ title, subtitle, actions, badges, back }: Props) {
  return (
    <header className="flex flex-col gap-1.5">
      {back ? (
        <Link
          to={back.to}
          className="inline-flex items-center gap-1 self-start text-xs text-text-subtle transition-colors duration-fast hover:text-text"
        >
          <ArrowLeft className="size-3.5" aria-hidden />
          {back.label}
        </Link>
      ) : null}
      <div className="flex min-h-control-md flex-wrap items-center gap-x-2.5 gap-y-2">
        <h1 className="flex min-w-0 items-center gap-2.5 text-lg font-bold">{title}</h1>
        {badges}
        {actions ? <div className="ml-auto flex items-center gap-2">{actions}</div> : null}
      </div>
      {subtitle ? <p className="max-w-prose text-sm text-text-subtle">{subtitle}</p> : null}
    </header>
  );
}
