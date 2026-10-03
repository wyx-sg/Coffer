// src/components/agents/overview/OverviewParts.tsx — the Overview's small building blocks: a label/value row, inline code, inline path.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface InfoRowProps {
  label: string;
  children: ReactNode;
  /** Monospace value — a path, a uid, a model id. */
  mono?: boolean;
  /** Right-aligned: a status word, a Test button. */
  trailing?: ReactNode;
}

/** One label / value line of a property section (Connection, Model, Details):
 *  hairline rows, label 13/500, value 13 muted. */
export function InfoRow({ label, children, mono, trailing }: InfoRowProps) {
  return (
    <div className="grid min-h-[41px] grid-cols-[172px_minmax(0,1fr)_auto] items-center gap-4 border-t border-border-subtle py-2">
      <dt className="text-sm font-medium text-text">{label}</dt>
      <dd
        className={cn(
          "min-w-0 break-words text-sm text-text-muted",
          mono && "break-all font-mono text-xs",
        )}
      >
        {children}
      </dd>
      <span className="justify-self-end">{trailing}</span>
    </div>
  );
}

/** A section's one-line description, 12 muted, between its title and its rows. */
export function SectionLine({ children }: { children: ReactNode }) {
  return <p className="-mt-1 mb-2.5 text-xs text-text-muted">{children}</p>;
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
