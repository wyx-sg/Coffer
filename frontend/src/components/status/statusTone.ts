// src/components/status/statusTone.ts — the four status tones and the statusColors vocabulary behind each.
import type { Tone } from "@/lib/statusColors";

/** Four tones only (Foundations-Status): ok, warn, err and off. */
export type StatusTone = "ok" | "warn" | "err" | "off";

export const STATUS_TONE: Record<StatusTone, Tone> = {
  ok: "ok",
  warn: "warn",
  err: "error",
  off: "muted",
};
