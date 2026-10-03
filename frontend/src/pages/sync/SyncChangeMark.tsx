// frontend/src/pages/sync/SyncChangeMark.tsx — the + ~ − that opens a file line.
//
// Green for added, grey for modified, red for removed (the boards colour the
// mark, never the path), in a fixed 10px column so paths line up.
import type { SyncChange } from "@/lib/api/sync";
import { cn } from "@/lib/utils";

const MARK: Record<string, { text: string; tone: string }> = {
  added: { text: "+", tone: "text-success" },
  removed: { text: "−", tone: "text-danger" },
};

export function ChangeMark({ status }: { status: SyncChange["status"] }) {
  const mark = MARK[status] ?? { text: "~", tone: "text-text-muted" };
  return (
    <span aria-hidden className={cn("w-2.5 shrink-0 font-mono text-xs", mark.tone)}>
      {mark.text}
    </span>
  );
}

/** The bordered list the Sync boards use for files: rows split by hairlines. */
export const FILE_LIST = "overflow-hidden rounded-xl border border-border bg-surface-raised";
export const FILE_ROW =
  "flex min-h-9 items-center gap-2.5 border-b border-border-subtle px-3 last:border-b-0";
