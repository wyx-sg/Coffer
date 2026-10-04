// frontend/src/pages/sync/SyncJoinLine.tsx — one line of a join preview: a mark, a title, a muted body.
// Lines sit in a bordered list (6.4.21 / 6.4.22), split by hairlines.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** The mark's colour when the line does not say: + green, ↑ accent, the rest quiet. */
const MARK_TONE: Record<string, string> = { "+": "text-success", "↑": "text-accent-text" };

export function JoinLine({
  mark,
  title,
  body,
  tone,
  testId,
}: {
  mark: string;
  title: ReactNode;
  body?: ReactNode;
  tone?: "warn" | "err";
  testId?: string;
}) {
  return (
    <li
      className="flex gap-3 border-b border-border-subtle px-3.5 py-2.5 last:border-b-0"
      data-testid={testId}
    >
      <span
        aria-hidden
        className={cn(
          "w-3 shrink-0 text-center font-mono text-sm font-semibold",
          tone === "warn"
            ? "text-warning"
            : tone === "err"
              ? "text-danger"
              : (MARK_TONE[mark] ?? "text-text-muted"),
        )}
      >
        {mark}
      </span>
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm font-medium text-text">{title}</span>
        {body ? <span className="text-xs text-text-muted">{body}</span> : null}
      </div>
    </li>
  );
}
