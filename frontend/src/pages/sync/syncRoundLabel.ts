// frontend/src/pages/sync/syncRoundLabel.ts
//
// What a round says in the Rounds table's "Round" column: a word for how it
// ended, beside the dot, and a muted clause that tells it apart — "Pulled and
// pushed · with Mac mini", "Stopped on 2 conflicts · nothing checked out or
// pushed", "Rolled back the 14:32 round · by you". A folded row says its
// outcome once and counts it: "Nothing to do ×6".
import type { TFunction } from "i18next";

import type { SyncRound } from "@/lib/api/sync";
import { clock } from "./syncTime";

export interface RoundLabel {
  main: string;
  detail: string | null;
}

/** Rounds that moved nothing either way: their Pulled and Pushed read "—", not 0. */
const MOVED_NOTHING = new Set<string>([
  "stopped",
  "held",
  "unreachable",
  "auth_failed",
  "rolled_back",
  "failed",
  "paused_cloud_folder",
  "remote_too_new",
  "join_required",
  "waiting_on_edit",
]);

/** The machines a round pulled from, in the order their commits arrived. */
function pulledFrom(round: SyncRound): string[] {
  const names = round.pulled.map((c) => c.machine).filter((m): m is string => Boolean(m));
  const unique = [...new Set(names)];
  return unique.length > 0 ? unique : round.with_machines;
}

/** The round a rollback undid: the one whose safety snapshot it went back to. */
export function rolledBackFrom(round: SyncRound, runs: SyncRound[]): SyncRound | null {
  if (round.status !== "rolled_back" || !round.snapshot) return null;
  return runs.find((r) => r.status !== "rolled_back" && r.snapshot === round.snapshot) ?? null;
}

/** The capitalised word for an outcome ("Pulled and pushed", "Remote unreachable"). */
export function outcomeLabel(t: TFunction, status: string): string {
  return t(`sync.rounds.label.${status}`, { defaultValue: status });
}

interface Context {
  runs: SyncRound[];
  /** The newest round, whose "retries at" is the next round the status names. */
  newest: boolean;
  nextRoundAt: string | null;
}

export function roundLabel(t: TFunction, round: SyncRound, ctx: Context): RoundLabel {
  const main = outcomeLabel(t, round.status);
  switch (round.status) {
    case "pulled_and_pushed":
      return {
        main,
        detail: round.with_machines.length
          ? t("sync.rounds.detail.with", { names: round.with_machines.join(", ") })
          : null,
      };
    case "pulled": {
      const from = pulledFrom(round);
      return {
        main,
        detail: from.length ? t("sync.rounds.detail.from", { names: from.join(", ") }) : null,
      };
    }
    case "push_failed":
      return {
        main: round.pulled_files > 0 ? t("sync.rounds.label.pulledPushFailed") : main,
        detail: t("sync.rounds.detail.rejected"),
      };
    case "plaintext_found":
      return { main, detail: t("sync.rounds.detail.plaintextKept") };
    case "stopped":
      return {
        main: t("sync.rounds.label.stoppedOn", { count: round.conflicts }),
        detail: t("sync.rounds.detail.nothingMoved"),
      };
    case "held":
      return {
        main: t("sync.rounds.label.heldCount", { count: round.held }),
        detail: t("sync.rounds.detail.nothingMoved"),
      };
    case "unreachable":
      return {
        main,
        detail:
          ctx.newest && ctx.nextRoundAt
            ? t("sync.rounds.detail.retriesAt", { time: clock(ctx.nextRoundAt) })
            : null,
      };
    case "pushed":
      return {
        main,
        detail: round.join === "replace" ? t("sync.rounds.detail.replacedRemote") : null,
      };
    case "auth_failed":
      return { main, detail: t("sync.rounds.detail.nothingPulledOrPushed") };
    case "rolled_back": {
      const undone = rolledBackFrom(round, ctx.runs);
      return {
        main: undone
          ? t("sync.rounds.label.rolledBackRound", { time: clock(undone.finished_at) })
          : main,
        detail: round.trigger === "manual" ? t("sync.rounds.detail.byYou") : null,
      };
    }
    default:
      return { main, detail: null };
  }
}

/** A round's Pulled and Pushed cells: counts, or "—" where the round moved nothing that way. */
export function movedCells(round: SyncRound): { pulled: string; pushed: string } {
  if (MOVED_NOTHING.has(round.status)) return { pulled: "—", pushed: "—" };
  if (round.status === "push_failed" || round.status === "plaintext_found")
    return { pulled: String(round.pulled_files), pushed: "—" };
  return { pulled: String(round.pulled_files), pushed: String(round.pushed_files) };
}

/** The Commits cell: `from..to`, or the snapshot a rollback went back to. */
export function commitsCell(round: SyncRound): string {
  if (round.status === "rolled_back") return round.snapshot ?? "";
  const short = (sha: string | null) => (sha ? sha.slice(0, 7) : "—");
  if (!round.from_commit && !round.to_commit) return "";
  return `${short(round.from_commit)}..${short(round.to_commit)}`;
}
