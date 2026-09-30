// frontend/src/components/knowledge/KnowledgeDiff.tsx
//
// A diff, rendered: old and new line numbers, a sign, the line — additions on
// the success role, deletions on the danger role, hunk headers muted. It takes
// rows (lib/knowledge/unifiedDiff.ts parses the daemon's unified diff,
// lib/knowledge/lineDiff.ts diffs a draft against the disk), so a change, a
// version and a stale-save compare all read the same way. It scrolls inside,
// both ways, rather than widening the pane.
import { useTranslation } from "react-i18next";

import type { DiffRow } from "@/lib/knowledge/unifiedDiff";
import { cn } from "@/lib/utils";

interface Props {
  rows: DiffRow[];
  className?: string;
}

const TONE: Record<DiffRow["kind"], string> = {
  hunk: "bg-surface-sunken text-text-subtle",
  context: "",
  add: "bg-success-soft",
  del: "bg-danger-soft",
};

const SIGN: Record<DiffRow["kind"], string> = { hunk: "", context: " ", add: "+", del: "−" };

export function KnowledgeDiff({ rows, className }: Props) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return <p className="px-3 py-2 text-xs text-text-subtle">{t("knowledge.diff.none")}</p>;
  }
  return (
    <div className={cn("overflow-auto rounded-md border border-border-subtle", className)}>
      <table className="w-full border-collapse font-mono text-xs leading-5">
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className={TONE[row.kind]}>
              <td className="w-10 select-none px-2 text-right align-top text-text-subtle">
                {row.oldLine ?? ""}
              </td>
              <td className="w-10 select-none px-2 text-right align-top text-text-subtle">
                {row.newLine ?? ""}
              </td>
              <td className="w-4 select-none align-top text-text-subtle">{SIGN[row.kind]}</td>
              <td className="whitespace-pre pr-3 align-top">{row.text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
