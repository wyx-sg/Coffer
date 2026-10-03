// src/components/agents/tabs/KindRow.tsx — one hairline row of an agent's own items (Skills, MCP servers, Plugins).
//
// A name (13/500 mono) over a muted one-line sub-line on the left; on the right
// whatever the row trails with — a state word, at most one button, a switch and
// the ⋯ menu. Rows sit in the bordered LIST_FRAME of AgentKindTab.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface Props {
  /** The name line (a link or button inside) — mono. */
  name: ReactNode;
  /** The line under the name: description, command, file. */
  sub?: ReactNode;
  /** Right side: state word, button, ⋯. */
  trailing?: ReactNode;
  className?: string;
}

export function KindRow({ name, sub, trailing, className }: Props) {
  return (
    <li
      className={cn(
        "flex items-center gap-3 border-b border-border-subtle px-4 py-2.5 last:border-b-0",
        className,
      )}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="min-w-0 truncate font-mono text-sm font-medium text-text">{name}</span>
        {sub ? (
          <span className="flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-text-muted">
            {sub}
          </span>
        ) : null}
      </div>
      {trailing ? (
        <div className="flex shrink-0 items-center justify-end gap-2">{trailing}</div>
      ) : null}
    </li>
  );
}

/** The " · " between the parts of a sub-line. */
export function Dot() {
  return (
    <span aria-hidden className="text-text-subtle">
      ·
    </span>
  );
}
