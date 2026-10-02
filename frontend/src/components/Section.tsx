// src/components/Section.tsx — the one titled block of a page or pane: a small
// heading with a muted meta line and/or trailing controls beside it, the content
// under them. The Memory overview, a provider's Overview, an agent's Overview
// and the agent Model tab all draw it.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface Props {
  title: string;
  /** Muted text beside the title, e.g. "Last 7 days" or "5 partitions · 79 memories". */
  meta?: ReactNode;
  /** Raw slot after the title (and meta): a help tip, a count, a link carrying its own `ml-auto`. */
  aside?: ReactNode;
  /** Right-aligned controls on the title's row — a "Change" or "All 412" link. */
  actions?: ReactNode;
  /** Space between the header and the content: 1.5, 2 or 2.5 (default). */
  gap?: "tight" | "snug" | "normal";
  /** Heading level; the page's own blocks are `h2`, a pane's are `h3` (default). */
  as?: "h2" | "h3";
  /** Names the section as a landmark after its title. */
  labelled?: boolean;
  testId?: string;
  className?: string;
  children: ReactNode;
}

const GAPS = { tight: "gap-1.5", snug: "gap-2", normal: "gap-2.5" } as const;

export function Section({
  title,
  meta,
  aside,
  actions,
  gap = "normal",
  as: Heading = "h3",
  labelled = false,
  testId,
  className,
  children,
}: Props) {
  return (
    <section
      className={cn("flex flex-col", GAPS[gap], className)}
      data-testid={testId}
      aria-label={labelled ? title : undefined}
    >
      <div className="flex min-h-control-sm items-center gap-2">
        <Heading className="text-sm font-semibold text-text">{title}</Heading>
        {meta ? <span className="text-xs text-text-muted">{meta}</span> : null}
        {aside}
        {actions ? <span className="ml-auto inline-flex items-center gap-2">{actions}</span> : null}
      </div>
      {children}
    </section>
  );
}
