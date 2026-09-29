// src/components/activity/ValueDiffBlock.tsx — a change's before and after as unified diff rows, in the change preview's look.
import type { ValueDiffLine } from "@/lib/activity/valueDiff";
import { cn } from "@/lib/utils";

export function ValueDiffBlock({ lines }: { lines: ValueDiffLine[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface-raised font-mono text-xs leading-5">
      {lines.map((line, index) =>
        line.kind === "gap" ? (
          <div
            key={index}
            className="border-y border-border-subtle bg-surface-sunken px-3 text-text-subtle"
          >
            {line.text}
          </div>
        ) : (
          <div
            key={index}
            data-line={line.kind}
            className={cn(
              "grid grid-cols-[30px_30px_14px_minmax(0,1fr)]",
              line.kind === "add" && "bg-success-soft",
              line.kind === "remove" && "bg-danger-soft",
            )}
          >
            <span className="pr-1.5 text-right text-2xs text-text-subtle">{line.oldNo ?? ""}</span>
            <span className="border-r border-border-subtle pr-1.5 text-right text-2xs text-text-subtle">
              {line.newNo ?? ""}
            </span>
            <span
              aria-hidden
              className={cn(
                "text-center",
                line.kind === "add" ? "text-success" : line.kind === "remove" ? "text-danger" : "",
              )}
            >
              {line.kind === "add" ? "+" : line.kind === "remove" ? "−" : ""}
            </span>
            <span className="whitespace-pre pr-2 text-text">{line.text}</span>
          </div>
        ),
      )}
    </div>
  );
}
