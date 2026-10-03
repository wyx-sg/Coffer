// src/components/PageHeader.tsx — the one page header for every surface.
//
// The boards draw one header (1.1.02 title bar, every list and detail board):
// one row — the title (18/650), anything that sits beside it (a count, a
// status, "Unsaved changes"), and the page's actions pushed to the right — and
// an optional subtitle line under the row. Pages carry no back button; the
// sidebar and the browser's own history are the way out. Detail pages keep one
// fixed action order: reach → test/refresh → edit → delete.
import type { ReactNode } from "react";

interface Props {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Right-aligned slot for the page's primary buttons, on the title's row. */
  actions?: ReactNode;
  /** Inline slot beside the title — a count, a status, a kind chip. */
  badges?: ReactNode;
}

export function PageHeader({ title, subtitle, actions, badges }: Props) {
  return (
    <header className="flex flex-col gap-1.5">
      <div className="flex min-h-control-md flex-wrap items-center gap-x-2.5 gap-y-2">
        <h1 className="flex min-w-0 items-center gap-2.5 text-lg font-bold">{title}</h1>
        {badges}
        {actions ? <div className="ml-auto flex items-center gap-2">{actions}</div> : null}
      </div>
      {subtitle ? <p className="truncate text-sm text-text-subtle">{subtitle}</p> : null}
    </header>
  );
}
