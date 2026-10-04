// src/components/change-preview/FileDiff.tsx
// The one diff renderer. One changed file: a header (agent badge — none for Coffer's own files, mono path, op
// chip, line counts) over its unified diff; `DiffLines` is the same block without the header, for callers that
// name the file elsewhere. A long line wraps at a word boundary and each continuation row carries a ↳ in the
// sign column over blank gutters (Foundations 0.6.05) — nothing is cut off and the view never widens its pane.
// With no lines at all the block reads "No changes to the text."
import { forwardRef } from "react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { wrapLine } from "@/lib/diff/wrapLine";
import { cn } from "@/lib/utils";
import { LineCounts } from "./LineCounts";
import { OpChip } from "./OpChip";
import type { ChangeItem, DiffLine } from "@/lib/changePreview/changeCounts";

const ROW_TONE: Record<DiffLine["kind"], string> = {
  context: "",
  hunk: "",
  add: "bg-success-soft",
  remove: "bg-danger-soft",
};

const SIGN: Record<DiffLine["kind"], { symbol: string; tone: string }> = {
  context: { symbol: "", tone: "text-text-subtle" },
  hunk: { symbol: "", tone: "text-text-subtle" },
  add: { symbol: "+", tone: "text-success" },
  remove: { symbol: "−", tone: "text-danger" },
};

const GUTTER = "pr-2 text-right text-2xs leading-5 text-text-subtle";

function DiffRow({ line, first }: { line: DiffLine; first: boolean }) {
  if (line.kind === "hunk") {
    return (
      <div
        data-line="hunk"
        className={cn(
          "truncate whitespace-nowrap border-b border-border-subtle bg-surface-sunken px-3 py-0.5 text-2xs leading-5 text-text-subtle",
          !first && "border-t",
        )}
      >
        {line.text}
      </div>
    );
  }
  const sign = SIGN[line.kind];
  return (
    <>
      {wrapLine(line.text).map((chunk, n) => (
        <div
          key={n}
          data-line={line.kind}
          data-continuation={n > 0 ? "true" : undefined}
          className={cn("grid grid-cols-[34px_34px_16px_minmax(0,1fr)]", ROW_TONE[line.kind])}
        >
          <span className={GUTTER}>{n === 0 ? (line.oldNo ?? "") : ""}</span>
          <span className={cn(GUTTER, "border-r border-border-subtle")}>
            {n === 0 ? (line.newNo ?? "") : ""}
          </span>
          <span aria-hidden className={cn("text-center", n === 0 ? sign.tone : "text-text-subtle")}>
            {n === 0 ? sign.symbol : "↳"}
          </span>
          <span className="whitespace-pre-wrap break-words pr-2.5 text-text">{chunk}</span>
        </div>
      ))}
    </>
  );
}

/** The bordered block of diff rows, without a file header. */
export function DiffLines({
  lines,
  className,
}: {
  lines: readonly DiffLine[];
  className?: string;
}) {
  const { t } = useTranslation();
  if (lines.length === 0) {
    return <p className="px-3 py-2 text-xs text-text-subtle">{t("diff.none")}</p>;
  }
  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border border-border bg-surface-raised font-mono text-xs leading-5",
        className,
      )}
    >
      {lines.map((line, index) => (
        <DiffRow key={index} line={line} first={index === 0} />
      ))}
    </div>
  );
}

interface Props {
  item: ChangeItem;
  className?: string;
  /** Say "No changes to the text." when the file has no lines, instead of showing the header alone. */
  showEmpty?: boolean;
}

export const FileDiff = forwardRef<HTMLElement, Props>(function FileDiff(
  { item, className, showEmpty = false },
  ref,
) {
  const { t } = useTranslation();
  return (
    <section
      ref={ref}
      aria-label={t("changePreview.diffLabel", { path: item.path })}
      data-change-id={item.id}
      className={cn("flex min-w-0 scroll-mt-4 flex-col gap-2.5", className)}
    >
      <div className="flex min-w-0 items-center gap-2">
        {item.agentType === "coffer" ? null : (
          <AgentBadge type={item.agentType} name={item.agentName} size="sm" className="shrink-0" />
        )}
        <span className="min-w-0 truncate font-mono text-xs font-medium text-text">
          {item.path}
        </span>
        <OpChip op={item.op} />
        <LineCounts added={item.added} removed={item.removed} className="ml-auto" />
      </div>
      {item.diff && item.diff.length > 0 ? (
        <DiffLines lines={item.diff} />
      ) : showEmpty ? (
        <DiffLines lines={[]} />
      ) : null}
    </section>
  );
});
