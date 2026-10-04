// frontend/src/lib/knowledge/documentConflict.ts
//
// What the editor says about a save the daemon refused as stale (boards 5.1.04,
// 5.1.29): the disk's text and fingerprint as the refusal carried them, and the
// sentences that name who changed the document and when, built from the newest
// version in its History when there is one — a part with no data is left out.
import type { TFunction } from "i18next";

import { ApiError } from "@/lib/api/errors";
import type { ChangeOut } from "@/lib/api/knowledge";
import { whenLabel, writerLabel } from "@/lib/knowledge/changes";

function detail(error: unknown, key: string): string | null {
  if (!(error instanceof ApiError)) return null;
  const value = (error.details as Record<string, unknown> | undefined)?.[key];
  return typeof value === "string" ? value : null;
}

/** The body on disk now, as the stale-save refusal carried it. */
export const currentBodyOf = (error: unknown): string | null => detail(error, "current_body");

/** The fingerprint on disk now, which a save over it must name. */
export const currentFingerprintOf = (error: unknown): string | null =>
  detail(error, "current_fingerprint");

function clock(iso: string, locale: string): string {
  return new Date(iso).toLocaleTimeString(locale, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** The banner's second line: who changed `file` and when, then that the text is not saved. */
export function conflictSentence(
  t: TFunction,
  change: ChangeOut | undefined,
  file: string,
  locale: string,
): string {
  if (!change) return t("knowledge.editor.conflictUnknown", { file });
  const time = clock(change.time, locale);
  return t("knowledge.editor.conflictOther", { file, time, who: writerLabel(t, change) });
}

/** The "take the disk" card's second line: who wrote it and when. */
export function diskMeta(t: TFunction, change: ChangeOut | undefined, locale: string): string {
  if (!change) return t("knowledge.compare.diskUnknown");
  return t("knowledge.compare.diskMeta", {
    who: writerLabel(t, change),
    when: whenLabel(t, change.time, locale),
  });
}
