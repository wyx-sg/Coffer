// src/components/secret/secretTimes.ts — how the Secrets page writes the day a secret was created.
//
// "Aug 12" (Foundations 0.3.03), with the year once it is a past year. Last used is a relative
// time (RelativeTime) and a secret never used here reads "Never". Pure: the clock is passed in.
import { formatUsDay } from "@/lib/time";

/** "Aug 12" in the UI's language; an unreadable timestamp is returned as given. */
export function shortDate(iso: string, lang: string, now = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return formatUsDay(d, lang, d.getFullYear() !== now.getFullYear());
}
