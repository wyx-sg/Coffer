// frontend/src/pages/sync/SyncDiffTable.tsx
//
// A unified diff as rows with old and new line numbers and tinted added and
// removed lines — the diff table the conflict view and a round's file rows share.
import type { DiffLine } from "@/lib/changePreview/changeCounts";
import { cn } from "@/lib/utils";

const GUTTER = "pr-2 text-right text-2xs leading-5 text-text-subtle";
const TONE: Record<DiffLine["kind"], string> = {
  context: "",
  hunk: "",
  add: "bg-success-soft",
  remove: "bg-danger-soft",
};
const SIGN: Record<DiffLine["kind"], [string, string]> = {
  context: ["", "text-text-subtle"],
  hunk: ["", "text-text-subtle"],
  add: ["+", "text-success"],
  remove: ["−", "text-danger"],
};

function Row({ line, first }: { line: DiffLine; first: boolean }) {
  if (line.kind === "hunk") {
    return (
      <div
        className={cn(
          "truncate whitespace-nowrap border-b border-border-subtle bg-surface-sunken px-3 py-0.5 text-2xs leading-5 text-text-subtle",
          !first && "border-t",
        )}
      >
        {line.text}
      </div>
    );
  }
  const [symbol, tone] = SIGN[line.kind];
  return (
    <div
      data-line={line.kind}
      className={cn("grid grid-cols-[34px_34px_16px_minmax(0,1fr)]", TONE[line.kind])}
    >
      <span className={GUTTER}>{line.oldNo ?? ""}</span>
      <span className={cn(GUTTER, "border-r border-border-subtle")}>{line.newNo ?? ""}</span>
      <span aria-hidden className={cn("text-center", tone)}>
        {symbol}
      </span>
      <span className="overflow-hidden text-ellipsis whitespace-pre pr-2.5 text-text">
        {line.text}
      </span>
    </div>
  );
}

export function DiffTable({
  lines,
  testId = "sync-conflict-diff",
}: {
  lines: DiffLine[];
  testId?: string;
}) {
  return (
    <div
      className="overflow-hidden rounded-lg border border-border bg-surface-raised font-mono text-xs leading-5"
      data-testid={testId}
    >
      {lines.map((line, i) => (
        <Row key={i} line={line} first={i === 0} />
      ))}
    </div>
  );
}
