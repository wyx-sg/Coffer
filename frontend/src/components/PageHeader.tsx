// src/components/PageHeader.tsx — the one page header for every surface.
//
// The boards draw one header (1.1.02 title bar, every list and detail board):
// one row — the title (18/650), anything that sits beside it (a count, a
// status, "Unsaved changes"), and the page's actions pushed to the right — and
// an optional subtitle line under the row. A page that is an experimental
// feature passes `experimental`: its tag sits 8px after the title (0.7.05).
// Pages carry no back button; the
// sidebar and the browser's own history are the way out. Detail pages keep one
// fixed action order: reach → test/refresh → edit → delete. An item ignored on
// Overview that belongs to the page shows under the subtitle (IgnoredHere).
import type { ReactNode } from "react";

import { ExperimentalTag } from "@/components/ExperimentalTag";
import { IgnoredHere } from "@/components/IgnoredHere";
import { useCanReadIgnored } from "@/lib/overview/useIgnoredHere";

interface Props {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Right-aligned slot for the page's primary buttons, on the title's row. */
  actions?: ReactNode;
  /** Inline slot beside the title — a count, a status, a kind chip. */
  badges?: ReactNode;
  /** Mark the page as an experimental feature: the "Experimental" tag right after the title. */
  experimental?: boolean;
}

export function PageHeader({ title, subtitle, actions, badges, experimental }: Props) {
  const canReadIgnored = useCanReadIgnored();
  return (
    <header className="flex flex-col gap-1.5">
      <div className="flex min-h-control-md flex-wrap items-center gap-x-2.5 gap-y-2">
        <h1 className="flex min-w-0 items-center gap-2.5 text-lg font-bold">{title}</h1>
        {experimental ? <ExperimentalTag className="-ml-0.5" /> : null}
        {badges}
        {actions ? <div className="ml-auto flex items-center gap-2">{actions}</div> : null}
      </div>
      {subtitle ? <p className="truncate text-sm text-text-subtle">{subtitle}</p> : null}
      {canReadIgnored ? <IgnoredHere /> : null}
    </header>
  );
}
