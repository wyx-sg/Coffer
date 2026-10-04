// frontend/src/lib/knowledge/lineDiff.ts
//
// A line diff between two texts, for Compare after a stale save: what is on
// disk now against the text the person typed. The daemon diffs only versions
// it has committed, and the person's draft is not one, so this runs here —
// a longest-common-subsequence over lines, which is exact and plenty fast for
// a document. Past `MAX_CELLS` it gives up on alignment and shows the old text
// removed and the new text added, rather than freezing the tab.
import type { DiffLine } from "@/lib/changePreview/changeCounts";

const MAX_CELLS = 4_000_000;

export function diffLines(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  const n = a.length;
  const m = b.length;
  if (n * m > MAX_CELLS) {
    return [
      ...a.map((text, i): DiffLine => ({ kind: "remove", text, oldNo: i + 1 })),
      ...b.map((text, j): DiffLine => ({ kind: "add", text, newNo: j + 1 })),
    ];
  }
  // lcs[i][j] = length of the LCS of a[i:] and b[j:], one flat array.
  const width = m + 1;
  const lcs = new Uint32Array((n + 1) * width);
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i * width + j] =
        a[i] === b[j]
          ? lcs[(i + 1) * width + j + 1] + 1
          : Math.max(lcs[(i + 1) * width + j], lcs[i * width + j + 1]);
    }
  }
  const rows: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      rows.push({ kind: "context", text: a[i], oldNo: i + 1, newNo: j + 1 });
      i++;
      j++;
    } else if (lcs[(i + 1) * width + j] >= lcs[i * width + j + 1]) {
      rows.push({ kind: "remove", text: a[i], oldNo: i + 1 });
      i++;
    } else {
      rows.push({ kind: "add", text: b[j], newNo: j + 1 });
      j++;
    }
  }
  for (; i < n; i++) rows.push({ kind: "remove", text: a[i], oldNo: i + 1 });
  for (; j < m; j++) rows.push({ kind: "add", text: b[j], newNo: j + 1 });
  return rows;
}
