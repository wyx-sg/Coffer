// frontend/src/components/skills/SkillRequireRow.tsx
// One row of the Requires tab (canvas 4.3.10): the name in mono, an optional
// Kind column (tools), a note, the state on the right and a link to the page
// that owns the thing ("View in CLIs"). The four groups share it so their
// columns line up (124 · [88] · fluid · 170 · 128).
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { cn } from "@/lib/utils";

interface Props {
  name: string;
  /** Present only for tools: MCP server / Custom tools. */
  kind?: string;
  note?: ReactNode;
  state: ReactNode;
  /** Where "View in …" leads, and its label; omitted when there is nowhere to go. */
  to?: string;
  linkLabel?: string;
  testId?: string;
}

export function SkillRequireRow({ name, kind, note, state, to, linkLabel, testId }: Props) {
  return (
    <li
      data-testid={testId}
      className={cn(
        "grid min-h-10 items-center gap-3 border-t border-border-subtle last:border-b",
        kind !== undefined
          ? "grid-cols-[124px_88px_minmax(0,1fr)_170px_128px]"
          : "grid-cols-[124px_minmax(0,1fr)_170px_128px]",
      )}
    >
      <span className="truncate font-mono text-xs font-label text-text">{name}</span>
      {kind !== undefined ? (
        <span className="whitespace-nowrap text-xs text-text-muted">{kind}</span>
      ) : null}
      <span className="min-w-0 truncate text-xs text-text-muted">{note}</span>
      <span>{state}</span>
      <span className="text-right">
        {to && linkLabel ? (
          <Link
            to={to}
            className="whitespace-nowrap text-xs font-label text-accent-text hover:underline"
          >
            {linkLabel}
          </Link>
        ) : null}
      </span>
    </li>
  );
}
