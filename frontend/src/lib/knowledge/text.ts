// frontend/src/lib/knowledge/text.ts
// Small pieces of wording the Knowledge page derives rather than stores: the
// progress label of a Curate now run, the description an item added from the
// web UI carries (the daemon requires one; the dialog has no field for it), a
// document's outline for the reader's "On this page", and an undo refusal in
// words.
import type { TFunction } from "i18next";

import { errorHandoff } from "@/lib/api/errorHandoff";
import { ApiError, translateApiError } from "@/lib/api/errors";

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

/** The refusal in words, the document that changed since when the daemon
 *  names it, and the prompt for undoing the pass by hand when it sends one. */
export function undoRefusal(
  t: TFunction,
  error: unknown,
): { text: string; document: string | null; handoff: string | null } {
  const handoff = errorHandoff(error);
  if (error instanceof ApiError && error.code === "KNOWLEDGE_UNDO_CONFLICT") {
    const document = (error.details as { document?: unknown } | undefined)?.document;
    if (typeof document === "string") {
      return { text: t("knowledge.pass.undoRefused", { document }), document, handoff };
    }
  }
  return { text: translateApiError(t, error), document: null, handoff };
}
