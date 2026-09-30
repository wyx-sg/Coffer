// frontend/src/lib/syncRoundToast.ts
//
// What a finished round's toast says. Stopped, held and failed rounds come
// back as a 200 carrying their story, so the HTTP status cannot decide the
// toast — the round's own status does.
import type { TFunction } from "i18next";

import type { RoundStatus, SyncRound } from "@/lib/api/sync";

export interface RoundToast {
  variant: "success" | "error" | "info";
  message: string;
}

/** Rounds that ended waiting on a person: news, not a failure. */
const NEEDS_ANSWER: ReadonlySet<RoundStatus> = new Set([
  "stopped",
  "held",
  "waiting_on_edit",
  "join_required",
]);

/** Rounds that could not do their job; `detail` carries git's own words. */
const FAILED: ReadonlySet<RoundStatus> = new Set([
  "push_failed",
  "unreachable",
  "auth_failed",
  "paused_cloud_folder",
  "remote_too_new",
  "remote_too_old",
  "failed",
]);

export function roundToast(t: TFunction, round: SyncRound): RoundToast {
  const status = t(`sync.round.status.${round.status}`, { defaultValue: round.status });
  if (NEEDS_ANSWER.has(round.status)) {
    return { variant: "info", message: t(`sync.toast.needs.${round.status}`) };
  }
  if (FAILED.has(round.status)) {
    return { variant: "error", message: round.detail ?? status };
  }
  return {
    variant: "success",
    message: t("sync.toast.roundDone", {
      status,
      pulled: round.pulled_files,
      pushed: round.pushed_files,
    }),
  };
}
