// frontend/src/components/knowledge/KnowledgeDiff.tsx
//
// A diff, rendered: old and new line numbers, a sign, the line — additions on
// the success role, deletions on the danger role, hunk headers muted. It takes
// rows (lib/knowledge/unifiedDiff.ts parses the daemon's unified diff,
// lib/knowledge/lineDiff.ts diffs a draft against the disk), so a change, a
// version and a stale-save compare all read the same way. A long line wraps at
// a word boundary and its continuation rows carry a ↳ in the sign column
// (Foundations 0.6.05) — nothing is cut off, and the view never widens the pane.
import { useTranslation } from "react-i18next";

import { wrapLine } from "@/lib/knowledge/wrapLine";
import type { DiffRow } from "@/lib/knowledge/unifiedDiff";
import { cn } from "@/lib/utils";

interface Props {
  rows: DiffRow[];
  className?: string;
}

const TONE: Record<DiffRow["kind"], string> = {
  hunk: "bg-surface-sunken text-2xs text-text-subtle",
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
    <div
      className={cn("overflow-auto rounded-lg border border-border bg-surface-raised", className)}
    >
      <table className="w-full border-collapse font-mono text-xs leading-5">
        <tbody>
          {rows.map((row, i) =>
            row.kind === "hunk" ? (
              <tr key={i} className={TONE.hunk}>
                <td colSpan={4} className="border-b border-border-subtle px-3 py-0.5">
                  {row.text}
                </td>
              </tr>
            ) : (
              wrapLine(row.text).map((chunk, n) => (
                <tr key={`${i}-${n}`} className={TONE[row.kind]}>
                  <td className="w-[34px] select-none pr-2 text-right align-top text-2xs text-text-subtle">
                    {n === 0 ? (row.oldLine ?? "") : ""}
                  </td>
                  <td className="w-[34px] select-none border-r border-border-subtle pr-2 text-right align-top text-2xs text-text-subtle">
                    {n === 0 ? (row.newLine ?? "") : ""}
                  </td>
                  <td
                    className={cn(
                      "w-4 select-none text-center align-top",
                      n > 0
                        ? "text-text-subtle"
                        : row.kind === "add"
                          ? "text-success"
                          : row.kind === "del"
                            ? "text-danger"
                            : "text-text-subtle",
                    )}
                  >
                    {n === 0 ? SIGN[row.kind] : "↳"}
                  </td>
                  <td className="whitespace-pre-wrap break-words pr-2.5 align-top">{chunk}</td>
                </tr>
              ))
            ),
          )}
        </tbody>
      </table>
    </div>
  );
}
