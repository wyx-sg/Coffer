// frontend/src/lib/statusColors.ts
//
// One semantic-state -> Tailwind colour vocabulary, shared by the MCP
// health badge and the invocations status badge so the two never drift.

type Tone = "ok" | "error" | "warn" | "muted";

const TONE_CLASS: Record<Tone, string> = {
  ok: "bg-green-100 text-green-900 dark:bg-green-950 dark:text-green-200",
  error: "bg-destructive/10 text-destructive",
  warn: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  muted: "bg-muted text-muted-foreground",
};

const HEALTH_TONE: Record<string, Tone> = {
  healthy: "ok",
  failing: "error",
  unknown: "muted",
};

const INVOCATION_TONE: Record<string, Tone> = {
  ok: "ok",
  error: "error",
  timeout: "warn",
  denied: "muted",
};

/** Badge class for an MCP server health state. */
export function healthStatusClass(state: string): string {
  return TONE_CLASS[HEALTH_TONE[state] ?? "muted"];
}

/** Badge class for an invocation status; "" for an unrecognised status. */
export function invocationStatusClass(status: string): string {
  const tone = INVOCATION_TONE[status];
  return tone ? TONE_CLASS[tone] : "";
}
