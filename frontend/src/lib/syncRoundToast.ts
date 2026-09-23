// frontend/src/lib/syncRoundToast.ts
//
// What a finished round's toast says. Held, conflicted, failed and not-yet-
// joined rounds come back as a 200 carrying their story, so the HTTP status
// cannot decide the toast — the round's own status does, in the same words
// the attention banner already uses for each situation.
import type { TFunction } from "i18next";

import type { ConvergeRound } from "@/lib/api/sync";

export interface RoundToast {
  variant: "success" | "error" | "info";
  message: string;
}

/** One finished round in a line: its status and what it moved both ways. */
function roundDone(t: TFunction, round: ConvergeRound): string {
  const applied = round.applied ?? { added: 0, modified: 0, deleted: 0 };
  const published = round.published ?? { added: 0, modified: 0, deleted: 0 };
  return t("sync.toast.roundDone", {
    status: t(`sync.round.statusLabel.${round.status}`, { defaultValue: round.status }),
    added: applied.added + published.added,
    modified: applied.modified + published.modified,
    deleted: applied.deleted + published.deleted,
  });
}

export function roundToast(t: TFunction, round: ConvergeRound): RoundToast {
  switch (round.status) {
    case "conflict":
      return { variant: "error", message: t("sync.attention.conflictBody") };
    case "push_failed":
      return { variant: "error", message: t("sync.attention.pushFailedBody") };
    case "failed":
      return { variant: "error", message: round.error ?? t("sync.attention.failedBody") };
    case "awaiting_confirmation":
      return { variant: "info", message: t("sync.attention.heldBody") };
    case "awaiting_join":
      return { variant: "info", message: t("sync.join.notJoined") };
    default:
      return { variant: "success", message: roundDone(t, round) };
  }
}
