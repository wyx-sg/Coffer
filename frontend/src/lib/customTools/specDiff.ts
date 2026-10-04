// src/lib/customTools/specDiff.ts — the old and new text of one operation as a unified diff for the shared diff
// rows: changed lines with a few lines of context, under one `@@` header. The daemon sends the two texts, not
// a patch, and not where the old one started: both sides count from where the new text starts.
import type { DiffLine } from "@/lib/changePreview/changeCounts";
import { diffLines } from "@/lib/knowledge/lineDiff";

/** Lines of context kept each side of a change. */
const CONTEXT = 3;

export interface SpecDiff {
  lines: DiffLine[];
  added: number;
  removed: number;
}

export function specDiff(oldText: string, newText: string, startLine: number): SpecDiff {
  const rows = diffLines(oldText, newText);
  const base = startLine - 1;
  const keep = rows.map(() => false);
  rows.forEach((row, i) => {
    if (row.kind === "context") return;
    for (let j = Math.max(0, i - CONTEXT); j <= Math.min(rows.length - 1, i + CONTEXT); j++) {
      keep[j] = true;
    }
  });
  const shown = rows.filter((_, i) => keep[i]);
  const oldCount = shown.filter((r) => r.kind !== "add").length;
  const newCount = shown.filter((r) => r.kind !== "remove").length;
  const first = shown[0];
  const oldFrom = (first?.oldNo ?? 1) + base;
  const newFrom = (first?.newNo ?? 1) + base;
  const lines: DiffLine[] = [];
  if (shown.length > 0) {
    lines.push({
      kind: "hunk",
      text: `@@ -${oldFrom},${oldCount} +${newFrom},${newCount} @@`,
    });
  }
  for (const row of shown) {
    lines.push({
      kind: row.kind,
      text: row.text,
      oldNo: row.oldNo === undefined ? undefined : row.oldNo + base,
      newNo: row.newNo === undefined ? undefined : row.newNo + base,
    });
  }
  return {
    lines,
    added: rows.filter((r) => r.kind === "add").length,
    removed: rows.filter((r) => r.kind === "remove").length,
  };
}
