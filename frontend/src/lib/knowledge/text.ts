// frontend/src/lib/knowledge/text.ts
// Two small pieces of wording the Knowledge page derives rather than stores:
// the progress label of a Curate now run, and the description an item added
// from the web UI carries (the daemon requires one; the dialog has no field
// for it).
import type { TFunction } from "i18next";

import type { UpkeepRunOut } from "@/lib/api/upkeep";

/** "Curating · 1 of 2" — the pass in flight, counted from one — or plain
 *  "Curating…" before the run reports its total. */
export function curatingLabel(t: TFunction, run: UpkeepRunOut | null): string {
  if (!run?.total) return t("knowledge.curate.running");
  const current = Math.min((run.done ?? 0) + 1, run.total);
  return t("knowledge.curate.progress", { done: current, total: run.total });
}

/** The body's first sentence (headings skipped, up to 160 characters), or the
 *  title when the body has none. */
export function describeItem(title: string, body: string): string {
  const text = body
    .replace(/^#+\s.*$/gm, "")
    .replace(/\s+/g, " ")
    .trim();
  const sentence = text.split(/(?<=[.!?。！？])\s/)[0] ?? "";
  return (sentence || title).slice(0, 160);
}
