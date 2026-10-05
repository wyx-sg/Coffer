// src/components/agents/tabs/KindRow.tsx — one row of an agent's own items (Skills, MCP servers, Plugins).
//
// A table row under AgentKindTab's header: the selection checkbox (when the
// list takes one), then one cell per column the tab declared, in that order.
// Every cell is one line — long text clips with TruncatedText — so rows keep a
// uniform height, as in the hooks table.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface Props {
  /** The row's selection checkbox (or its spacer); null when the list takes none. */
  leading?: ReactNode;
  /** One cell per column, in the order AgentKindTab's `columns` lists them. */
  cells: ReactNode[];
  className?: string;
}

export function KindRow({ leading, cells, className }: Props) {
  const hasLeading = leading !== undefined && leading !== null;
  return (
    <tr className={cn("border-b border-border-subtle last:border-b-0", className)}>
      {hasLeading ? <td className="py-2.5 pl-4 pr-1 align-middle">{leading}</td> : null}
      {cells.map((cell, i) => (
        <td
          key={i}
          className={cn(
            "min-w-0 py-2.5 align-middle text-xs text-text-muted",
            i === 0 && !hasLeading ? "pl-4 pr-2" : "px-2",
            i === cells.length - 1 && "pr-4",
          )}
        >
          {cell}
        </td>
      ))}
    </tr>
  );
}

/** A row's name cell: 13/500 mono, one line. */
export function KindName({ children }: { children: ReactNode }) {
  return (
    <span className="block min-w-0 truncate font-mono text-sm font-medium text-text">
      {children}
    </span>
  );
}

/** A trailing cell's controls (state word, button, switch, ⋯), right-aligned. */
export function KindActions({ children }: { children: ReactNode }) {
  return <div className="flex items-center justify-end gap-2">{children}</div>;
}
