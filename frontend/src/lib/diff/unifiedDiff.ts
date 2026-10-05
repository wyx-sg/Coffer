// frontend/src/lib/diff/unifiedDiff.ts
//
// Parse the unified diff the daemon hands back for one file of a vault
// version (`git show --patch` / `git diff` over one path) into lines FileDiff,
// the one diff renderer, can number and colour. The git headers
// (`diff --git`, `index`, `---` / `+++`, mode lines) are dropped: the view
// already names the file. A "\ No newline at end of file" marker is dropped
// too — it is about bytes, not about the text.
import type { DiffLine } from "@/lib/changePreview/changeCounts";

const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$/;

export function parseUnifiedDiff(diff: string): DiffLine[] {
  const rows: DiffLine[] = [];
  let oldLine = 0;
  let newLine = 0;
  let inHunk = false;
  for (const line of diff.split("\n")) {
    const hunk = HUNK.exec(line);
    if (hunk) {
      inHunk = true;
      oldLine = Number(hunk[1]);
      newLine = Number(hunk[2]);
      rows.push({ kind: "hunk", text: line });
      continue;
    }
    if (!inHunk || line.startsWith("\\")) continue;
    if (line.startsWith("+")) {
      rows.push({ kind: "add", text: line.slice(1), newNo: newLine++ });
    } else if (line.startsWith("-")) {
      rows.push({ kind: "remove", text: line.slice(1), oldNo: oldLine++ });
    } else if (line.startsWith(" ")) {
      rows.push({ kind: "context", text: line.slice(1), oldNo: oldLine++, newNo: newLine++ });
    } else if (line.startsWith("diff --git")) {
      // A second file's header: stop numbering until its first hunk.
      inHunk = false;
    }
  }
  return rows;
}
