// frontend/src/lib/statusColors.ts
//
// One semantic-state -> Tailwind colour vocabulary, shared by the MCP
// health badge and the channels table so the two never drift.

type Tone = "ok" | "error" | "muted";

const TONE_CLASS: Record<Tone, string> = {
  ok: "bg-green-100 text-green-900 dark:bg-green-950 dark:text-green-200",
  error: "bg-destructive/10 text-destructive",
  muted: "bg-muted text-muted-foreground",
};

const HEALTH_TONE: Record<string, Tone> = {
  healthy: "ok",
  failing: "error",
  unknown: "muted",
};

/** Badge class for an MCP server health state. */
export function healthStatusClass(state: string): string {
  return TONE_CLASS[HEALTH_TONE[state] ?? "muted"];
}
