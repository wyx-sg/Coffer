// frontend/src/pages/sync/SyncJoinLine.tsx — one line of a join preview: a mark, a title, a muted body.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

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
      className="flex gap-3 border-t border-border-subtle py-2.5 first:border-t-0"
      data-testid={testId}
    >
      <span
        aria-hidden
        className={cn(
          "w-4 shrink-0 text-center font-mono text-sm",
          tone === "warn" ? "text-warning" : tone === "err" ? "text-danger" : "text-text-muted",
        )}
      >
        {mark}
      </span>
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm font-label text-text">{title}</span>
        {body ? <span className="text-xs text-text-muted">{body}</span> : null}
      </div>
    </li>
  );
}
