// src/lib/conversations/toolSummary.ts
// The one line a collapsed tool call shows beside its name — what it was called
// on: the file, the pattern, the command, the URL — so a reply's steps read at a
// glance without opening each card. Pure; unknown tools fall back to their
// first short string argument.
const PREFERRED = ["file_path", "path", "notebook_path", "command", "pattern", "url", "query"];
const MAX = 120;

function oneLine(value: string): string {
  const flat = value.replace(/\s+/g, " ").trim();
  return flat.length > MAX ? `${flat.slice(0, MAX - 1)}…` : flat;
}

export function toolSummary(input: Record<string, unknown> | null | undefined): string {
  if (!input) return "";
  const parts: string[] = [];
  for (const key of PREFERRED) {
    const v = input[key];
    if (typeof v === "string" && v) parts.push(key === "pattern" ? `"${v}"` : v);
    if (parts.length === 2) break;
  }
  if (parts.length === 0) {
    const first = Object.values(input).find((v) => typeof v === "string" && v.length > 0);
    if (typeof first === "string") parts.push(first);
  }
  if (parts.length === 0 && Array.isArray(input.changes)) {
    const paths = (input.changes as Record<string, unknown>[])
      .map((c) => c.path)
      .filter((p): p is string => typeof p === "string");
    parts.push(paths.join(", "));
  }
  return oneLine(parts.join(" · "));
}
