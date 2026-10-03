// src/components/agents/tabs/TabEmpty.tsx — the empty state of an agent's list tabs (board 2.1.55).
//
// A bordered rounded box, a 13/600 title and one 12 muted line, centred, no icon.
// Skills, MCP servers, Plugins, Hooks and Memory all say "nothing here" this way.
import type { ReactNode } from "react";

interface Props {
  title: string;
  description?: ReactNode;
}

export function TabEmpty({ title, description }: Props) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-lg border border-border bg-surface-raised px-6 py-8 text-center">
      <p className="text-sm font-semibold text-text">{title}</p>
      {description ? <p className="text-xs text-text-muted">{description}</p> : null}
    </div>
  );
}
