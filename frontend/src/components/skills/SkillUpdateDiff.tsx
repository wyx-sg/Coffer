// src/components/skills/SkillUpdateDiff.tsx
// One changed file of a skill update: its path, operation and line counts over the unified diff the daemon computed.
//
// The rows take the change-preview look (Foundations-ChangePreview): an added
// line on the success-soft fill, a removed one on danger-soft, hunk headers on
// the sunken fill, old and new line numbers in the gutter.
import { useTranslation } from "react-i18next";

import { LineCounts } from "@/components/change-preview/LineCounts";
import { OpChip } from "@/components/change-preview/OpChip";
import type { DiffLine } from "@/lib/changePreview/changeCounts";
import type { SkillFileChange } from "@/lib/api/skills";
import { cn } from "@/lib/utils";
import { CHANGE_OP, parseUnifiedDiff } from "./skillSourceHelpers";

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

function Row({ line, first }: { line: DiffLine; first: boolean }) {
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
    <div
      data-line={line.kind}
      className={cn("grid grid-cols-[34px_34px_16px_minmax(0,1fr)]", ROW_TONE[line.kind])}
    >
      <span className={GUTTER}>{line.oldNo ?? ""}</span>
      <span className={cn(GUTTER, "border-r border-border-subtle")}>{line.newNo ?? ""}</span>
      <span aria-hidden className={cn("text-center", sign.tone)}>
        {sign.symbol}
      </span>
      <span className="overflow-hidden text-ellipsis whitespace-pre pr-2.5 text-text">
        {line.text}
      </span>
    </div>
  );
}

interface Props {
  change: SkillFileChange;
}

export function SkillUpdateDiff({ change }: Props) {
  const { t } = useTranslation();
  const lines = change.binary ? [] : parseUnifiedDiff(change.diff);
  return (
    <section
      aria-label={t("skillSources.update.diffLabel", { path: change.path })}
      className="flex min-w-0 flex-col gap-2.5"
    >
      <div className="flex min-w-0 items-center gap-2">
        <span className="min-w-0 truncate font-mono text-xs font-medium text-text">
          {change.path}
        </span>
        <OpChip op={CHANGE_OP[change.status]} />
        <LineCounts added={change.additions} removed={change.deletions} className="ml-auto" />
      </div>
      {change.binary ? (
        <p className="text-xs text-text-muted">{t("skillSources.update.binary")}</p>
      ) : lines.length > 0 ? (
        <div className="overflow-hidden rounded-lg border border-border bg-surface-raised font-mono text-xs leading-5">
          {lines.map((line, index) => (
            <Row key={index} line={line} first={index === 0} />
          ))}
        </div>
      ) : (
        <p className="text-xs text-text-muted">{t("skillSources.update.noDiff")}</p>
      )}
      {change.truncated ? (
        <p className="text-xs text-text-muted">{t("skillSources.update.truncated")}</p>
      ) : null}
    </section>
  );
}
