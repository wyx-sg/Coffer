// frontend/src/components/skills/textDiff.ts
// Two texts as a change preview's diff: the lines that differ with a few
// lines of context around each run, and an `@@ -a,b +c,d @@` header over each
// hunk, so a long file whose edit is two lines reads as two lines. Used where
// the daemon has no diff to hand — a draft against the file on disk, a copy's
// text against the master (the daemon diffs only what it has committed).
import type { ChangeItem, ChangeOp, DiffLine } from "@/lib/changePreview/changeCounts";
import { diffLines } from "@/lib/knowledge/lineDiff";

const CONTEXT = 3;

interface TextDiff {
  lines: DiffLine[];
  added: number;
  removed: number;
}

export function textDiff(before: string, after: string): TextDiff {
  const rows = diffLines(before, after);
  const changed = rows.map((r) => r.kind !== "context");
  const keep = new Array<boolean>(rows.length).fill(false);
  changed.forEach((isChange, i) => {
    if (!isChange) return;
    for (let k = Math.max(0, i - CONTEXT); k <= Math.min(rows.length - 1, i + CONTEXT); k++) {
      keep[k] = true;
    }
  });

  const lines: DiffLine[] = [];
  let added = 0;
  let removed = 0;
  let i = 0;
  while (i < rows.length) {
    if (!keep[i]) {
      i++;
      continue;
    }
    // One hunk: the run of kept rows.
    let end = i;
    while (end < rows.length && keep[end]) end++;
    const hunk = rows.slice(i, end);
    const oldStart = hunk.find((r) => r.oldLine !== undefined)?.oldLine ?? 0;
    const newStart = hunk.find((r) => r.newLine !== undefined)?.newLine ?? 0;
    const oldCount = hunk.filter((r) => r.kind !== "add").length;
    const newCount = hunk.filter((r) => r.kind !== "del").length;
    lines.push({
      kind: "hunk",
      text: `@@ −${oldStart},${oldCount} +${newStart},${newCount} @@`,
    });
    for (const r of hunk) {
      if (r.kind === "add") {
        added++;
        lines.push({ kind: "add", text: r.text, newNo: r.newLine });
      } else if (r.kind === "del") {
        removed++;
        lines.push({ kind: "remove", text: r.text, oldNo: r.oldLine });
      } else {
        lines.push({ kind: "context", text: r.text, oldNo: r.oldLine, newNo: r.newLine });
      }
    }
    i = end;
  }
  return { lines, added, removed };
}

/** A change preview item for one file's text change. */
export function textChangeItem(
  id: string,
  path: string,
  before: string,
  after: string,
  agent: { type: string; name?: string } = { type: "coffer" },
  op: ChangeOp = "modify",
): ChangeItem {
  const d = textDiff(before, after);
  return {
    id,
    agentType: agent.type,
    agentName: agent.name,
    path,
    op,
    added: d.added,
    removed: d.removed,
    diff: d.lines,
  };
}
