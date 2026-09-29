// src/lib/activity/valueDiff.ts — a line diff of a change's before and after, for the record drawer.
//
// An audit entry for an edit carries the resource's config before and after
// the write (already stripped of secret values by the daemon). The drawer
// shows what changed as a unified diff of the two pretty-printed values, the
// same add / remove / context rows the change preview draws.

/** @ui-only One row of a line diff. */
export interface ValueDiffLine {
  kind: "context" | "add" | "remove" | "gap";
  text: string;
  oldNo?: number;
  newNo?: number;
}

/** Past this many lines a side is shown whole rather than diffed. */
const MAX_LINES = 600;
/** Unchanged lines kept around each change. */
const CONTEXT = 2;

export function prettyValue(value: unknown): string {
  return JSON.stringify(value ?? null, null, 2);
}

/** The longest common subsequence table, bottom-up. */
function lcs(a: readonly string[], b: readonly string[]): number[][] {
  const table = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i][j] =
        a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  return table;
}

/**
 * The diff of two values, changed lines with `CONTEXT` lines around them and a
 * `gap` row where unchanged lines were left out. Equal values give [].
 */
export function diffValues(before: unknown, after: unknown): ValueDiffLine[] {
  const a = prettyValue(before).split("\n");
  const b = prettyValue(after).split("\n");
  if (a.join("\n") === b.join("\n")) return [];
  const full: ValueDiffLine[] = [];
  if (a.length > MAX_LINES || b.length > MAX_LINES) {
    a.forEach((text, i) => full.push({ kind: "remove", text, oldNo: i + 1 }));
    b.forEach((text, i) => full.push({ kind: "add", text, newNo: i + 1 }));
    return full;
  }
  const table = lcs(a, b);
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      full.push({ kind: "context", text: a[i], oldNo: i + 1, newNo: j + 1 });
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      full.push({ kind: "remove", text: a[i], oldNo: i + 1 });
      i += 1;
    } else {
      full.push({ kind: "add", text: b[j], newNo: j + 1 });
      j += 1;
    }
  }
  for (; i < a.length; i += 1) full.push({ kind: "remove", text: a[i], oldNo: i + 1 });
  for (; j < b.length; j += 1) full.push({ kind: "add", text: b[j], newNo: j + 1 });

  // Keep only the context near a change.
  const near = full.map(() => false);
  full.forEach((line, index) => {
    if (line.kind === "context") return;
    for (
      let k = Math.max(0, index - CONTEXT);
      k <= Math.min(full.length - 1, index + CONTEXT);
      k += 1
    ) {
      near[k] = true;
    }
  });
  const out: ValueDiffLine[] = [];
  full.forEach((line, index) => {
    if (near[index]) out.push(line);
    else if (out.length === 0 || out[out.length - 1].kind !== "gap") {
      out.push({ kind: "gap", text: "…" });
    }
  });
  if (out.length > 0 && out[out.length - 1].kind === "gap") out.pop();
  return out;
}

/** Added and removed line counts. */
export function diffCounts(lines: readonly ValueDiffLine[]): { added: number; removed: number } {
  let added = 0;
  let removed = 0;
  for (const line of lines) {
    if (line.kind === "add") added += 1;
    else if (line.kind === "remove") removed += 1;
  }
  return { added, removed };
}
