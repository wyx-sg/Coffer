// src/lib/chat/unifiedDiff.ts
// A unified diff as the diff drawer draws it: hunks, each with its header text
// and rows of {old number, new number, kind, text}. Handles several hunks, the
// "\ No newline at end of file" marker (dropped), and the concatenated diffs
// Codex records for one path (several `---` / `+++` blocks). Each hunk's own
// counts say when its rows end, so a removed line that reads `-- x` is never
// mistaken for a file header. Pure.

export interface DiffRow {
  kind: "context" | "add" | "del";
  oldNo: number | null;
  newNo: number | null;
  text: string;
}

export interface DiffHunk {
  /** The whole `@@ -a,b +c,d @@ section` line. */
  header: string;
  rows: DiffRow[];
}

const HUNK = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/;

export function parseUnifiedDiff(diff: string): DiffHunk[] {
  const hunks: DiffHunk[] = [];
  let current: DiffHunk | null = null;
  let oldNo = 0;
  let newNo = 0;
  let oldLeft = 0;
  let newLeft = 0;
  for (const line of diff.split("\n")) {
    if (line.startsWith("\\")) continue; // "\ No newline at end of file"
    const open = current !== null && (oldLeft > 0 || newLeft > 0);
    if (!open) {
      const head = HUNK.exec(line);
      if (!head) continue; // file headers and anything else between hunks
      current = { header: line, rows: [] };
      hunks.push(current);
      oldNo = Number(head[1]);
      newNo = Number(head[3]);
      oldLeft = head[2] === undefined ? 1 : Number(head[2]);
      newLeft = head[4] === undefined ? 1 : Number(head[4]);
      continue;
    }
    const rows = current!.rows;
    const marker = line[0];
    const text = line.slice(1);
    if (marker === "+") {
      rows.push({ kind: "add", oldNo: null, newNo: newNo++, text });
      newLeft -= 1;
    } else if (marker === "-") {
      rows.push({ kind: "del", oldNo: oldNo++, newNo: null, text });
      oldLeft -= 1;
    } else {
      // A context line; an empty one is a context line whose space was trimmed.
      rows.push({ kind: "context", oldNo: oldNo++, newNo: newNo++, text });
      oldLeft -= 1;
      newLeft -= 1;
    }
  }
  return hunks;
}
