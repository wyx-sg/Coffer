// src/lib/agents/configFiles.ts — small pure helpers for the agent's Config files tab.
//
// `checkJson`: where a JSON draft stops being valid. The daemon validates every config write and refuses malformed JSON (422), so
// this is not a guard — it is the editor saying where the problem is while the
// user types, and holding Save back until the draft parses. Only the position
// is taken from the engine's error: its wording is English and engine-specific,
// so the message itself comes from the caller's translation.

export type JsonCheck = { ok: true } | { ok: false; line: number; column: number };

/** The 1-based line and column of `offset` in `text`. */
function lineColumn(text: string, offset: number): { line: number; column: number } {
  const before = text.slice(0, offset);
  const lines = before.split("\n");
  return { line: lines.length, column: lines[lines.length - 1].length + 1 };
}

export function checkJson(text: string): JsonCheck {
  try {
    JSON.parse(text);
    return { ok: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : "";
    const lc = /line (\d+) column (\d+)/.exec(message);
    if (lc) return { ok: false, line: Number(lc[1]), column: Number(lc[2]) };
    const pos = /position (\d+)/.exec(message);
    if (pos) return { ok: false, ...lineColumn(text, Number(pos[1])) };
    // No position reported (an empty draft, "Unexpected end of JSON input"): the end.
    return { ok: false, ...lineColumn(text, text.length) };
  }
}

/** The last segment of a path — the name the agent's own docs use for the file. */
export function baseName(path: string): string {
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}
