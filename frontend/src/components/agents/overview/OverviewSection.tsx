// src/components/agents/overview/OverviewSection.tsx — the Overview's building blocks: a titled section, a label/value row, inline code.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface SectionProps {
  title: string;
  /** Right-aligned beside the title — a "Change" or "All 412" link. */
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function OverviewSection({ title, aside, children, className }: SectionProps) {
  return (
    <section className={cn("flex flex-col gap-2.5", className)}>
      <div className="flex min-h-[26px] items-center gap-2">
        <h3 className="text-sm font-semibold text-text">{title}</h3>
        {aside ? <span className="ml-auto inline-flex items-center gap-2">{aside}</span> : null}
      </div>
      {children}
    </section>
  );
}

interface InfoRowProps {
  label: string;
  children: ReactNode;
  /** Monospace value — a path, a uid, a model id. */
  mono?: boolean;
}

/** One label/value line of the Model, Details and last-known lists. */
export function InfoRow({ label, children, mono }: InfoRowProps) {
  return (
    <div className="grid grid-cols-[110px_minmax(0,1fr)] items-baseline gap-4 border-t border-border-subtle py-[7px]">
      <dt className="text-xs text-text-subtle">{label}</dt>
      <dd
        className={cn(
          "min-w-0 break-words text-sm text-text",
          mono && "break-all font-mono text-xs",
        )}
      >
        {children}
      </dd>
    </div>
  );
}

/** A code chip inside running text — an entry name, a file, a program. */
export function InlineCode({ children }: { children?: ReactNode }) {
  return (
    <code className="break-all rounded-xs bg-code px-[5px] py-px font-mono text-xs text-text">
      {children}
    </code>
  );
}

/** A path inside running text, without the chip. */
export function InlinePath({ children }: { children?: ReactNode }) {
  return <span className="break-all font-mono text-xs">{children}</span>;
}
