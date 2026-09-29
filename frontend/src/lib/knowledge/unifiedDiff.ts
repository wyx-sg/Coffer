// frontend/src/lib/knowledge/unifiedDiff.ts
//
// Parse the unified diff the daemon hands back for a change or a version
// (`git show --patch` over one document) into rows a diff view can number and
// colour. The git headers (`diff --git`, `index`, `---` / `+++`, mode lines)
// are dropped: the view already names the document. A "\ No newline at end of
// file" marker is dropped too — it is about bytes, not about the text.

type DiffRowKind = "hunk" | "context" | "add" | "del";

/** One row of a rendered diff. */
export interface DiffRow {
  kind: DiffRowKind;
  text: string;
  /** Line number before the change (context and deletions). */
  oldLine?: number;
  /** Line number after the change (context and additions). */
  newLine?: number;
}

const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$/;

export function parseUnifiedDiff(diff: string): DiffRow[] {
  const rows: DiffRow[] = [];
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
      rows.push({ kind: "add", text: line.slice(1), newLine: newLine++ });
    } else if (line.startsWith("-")) {
      rows.push({ kind: "del", text: line.slice(1), oldLine: oldLine++ });
    } else if (line.startsWith(" ")) {
      rows.push({ kind: "context", text: line.slice(1), oldLine: oldLine++, newLine: newLine++ });
    } else if (line.startsWith("diff --git")) {
      // A second file's header: stop numbering until its first hunk.
      inHunk = false;
    }
  }
  return rows;
}
