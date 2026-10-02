// src/components/Section.tsx — the one titled block of a page or pane, and the
// stack that separates several of them.
//
// A Section is a heading (one size everywhere), an optional "?" help tip beside
// it that holds the explanation, trailing controls on the right, and the
// content. It prints no sentence under the title and no count beside it: what
// the block is for rides in `help`, how many it holds is in the content. A
// SectionStack lays Sections one above the other with a hairline between each,
// so every pane that stacks blocks divides them the same way.
import type { ReactNode } from "react";

import { HelpTip } from "@/components/HelpTip";
import { cn } from "@/lib/utils";

interface Props {
  title: string;
  /** What the block is for — shown in a "?" tip beside the title, never inline. */
  help?: ReactNode;
  /** Raw slot after the title (and help tip), e.g. a link carrying its own `ml-auto`. Not for counts. */
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
  help,
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
        {help ? <HelpTip>{help}</HelpTip> : null}
        {aside}
        {actions ? <span className="ml-auto inline-flex items-center gap-2">{actions}</span> : null}
      </div>
      {children}
    </section>
  );
}

/** Sections one above the other, a hairline between each (the right-hand panes' one divider style). */
export function SectionStack({
  children,
  className,
  testId,
}: {
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col divide-y divide-border [&>*]:py-5 [&>*:first-child]:pt-0 [&>*:last-child]:pb-0",
        className,
      )}
      data-testid={testId}
    >
      {children}
    </div>
  );
}
