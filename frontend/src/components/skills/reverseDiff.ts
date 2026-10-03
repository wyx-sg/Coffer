// frontend/src/components/skills/reverseDiff.ts
// A diff read the other way round: what undoing the change would do. Added
// lines become removed ones and back, each line's two numbers swap, and a
// hunk's two ranges swap. Restore uses it — putting an older version back is
// the newer versions' diffs reversed.
import type { DiffLine } from "@/lib/changePreview/changeCounts";

export function reverseDiffLines(lines: readonly DiffLine[]): DiffLine[] {
  return lines.map((line): DiffLine => {
    if (line.kind === "hunk") {
      const m = /^@@ [−-](\S+) \+(\S+) @@(.*)$/.exec(line.text);
      return m ? { ...line, text: `@@ −${m[2]} +${m[1]} @@${m[3]}` } : line;
    }
    const swapped = { oldNo: line.newNo, newNo: line.oldNo };
    if (line.kind === "add") return { kind: "remove", text: line.text, ...swapped };
    if (line.kind === "remove") return { kind: "add", text: line.text, ...swapped };
    return { ...line, ...swapped };
  });
}
