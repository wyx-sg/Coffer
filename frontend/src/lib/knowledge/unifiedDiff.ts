// frontend/src/lib/knowledge/unifiedDiff.ts
//
// Parse the unified diff the daemon hands back for a change or a version
// (`git show --patch` over one document) into lines a diff view can number and
// colour (the shared DiffLine of the change preview, so FileDiff renders them).
// The git headers (`diff --git`, `index`, `---` / `+++`, mode lines) are dropped: the view already names the document. A "\ No newline at end of
// file" marker is dropped too — it is about bytes, not about the text.

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
