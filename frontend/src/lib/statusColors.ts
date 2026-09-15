// frontend/src/lib/statusColors.ts
//
// One semantic-state -> Tailwind colour vocabulary, shared by the MCP
// health badge, the invocations status badge and the channels table so they
// never drift. Built on the status.ok|warn|err tokens (visual-language.md),
// never the raw palette.

export type Tone = "ok" | "error" | "warn" | "muted";

const TONE_CLASS: Record<Tone, string> = {
  ok: "bg-status-ok/15 text-status-ok",
  error: "bg-destructive/10 text-destructive",
  warn: "bg-status-warn/15 text-status-warn",
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

/** Badge class for a semantic tone the caller has already chosen — the
 * Activity page's Daemon tab maps a structlog level onto this vocabulary so an
 * error line reads the same red as a failed call does everywhere else. */
export function toneClass(tone: Tone): string {
  return TONE_CLASS[tone];
}

/** Badge class for an MCP server health state. */
export function healthStatusClass(state: string): string {
  return TONE_CLASS[HEALTH_TONE[state] ?? "muted"];
}

/** Badge class for an invocation status; "" for an unrecognised status. */
export function invocationStatusClass(status: string): string {
  const tone = INVOCATION_TONE[status];
  return tone ? TONE_CLASS[tone] : "";
}
