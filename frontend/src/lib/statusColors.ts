// frontend/src/lib/statusColors.ts
//
// One semantic-state -> Tailwind colour vocabulary, shared by the MCP
// health badge, the invocations status badge and the channels table so they
// never drift. Built on the Foundations status roles (success / warning /
// danger / neutral and their -soft fills), never the raw palette. StatusDot,
// StatusWord and StatusPill reuse the same tones through `toneDotClass` /
// `toneTextClass`.

export type Tone = "ok" | "error" | "warn" | "muted";

const TONE_CLASS: Record<Tone, string> = {
  ok: "bg-success-soft text-success",
  error: "bg-danger-soft text-danger",
  warn: "bg-warning-soft text-warning",
  muted: "bg-neutral-soft text-text-muted",
};

// The solid dot colour per tone — the dot always carries the status colour,
// even where the word beside it stays quiet.
const TONE_DOT: Record<Tone, string> = {
  ok: "bg-success",
  error: "bg-danger",
  warn: "bg-warning",
  muted: "bg-neutral",
};

// A status word's colour: healthy and off read quietly in muted text, a
// problem takes its status colour (Foundations-Status "dot + word").
const TONE_TEXT: Record<Tone, string> = {
  ok: "text-text-muted",
  error: "text-danger",
  warn: "text-warning",
  muted: "text-text-muted",
};

/** Badge class for a semantic tone the caller has already chosen — the
 * Activity page's Daemon tab maps a structlog level onto this vocabulary so an
 * error line reads the same red as a failed call does everywhere else. */
export function toneClass(tone: Tone): string {
  return TONE_CLASS[tone];
}

/** Solid dot class (`bg-success` …) for a tone. */
export function toneDotClass(tone: Tone): string {
  return TONE_DOT[tone];
}

/** Word colour for a tone beside its dot: muted when ok or off. */
export function toneTextClass(tone: Tone): string {
  return TONE_TEXT[tone];
}
