// frontend/src/pages/sync/syncProblemRounds.ts — the newest round that got
// through to the remote, for the unreachable card's "no round has finished since".
import type { SyncRound } from "@/lib/api/sync";

/** Outcomes of a round that got through to the remote. */
const GOT_THROUGH = new Set<string>([
  "nothing_to_do",
  "pulled",
  "pushed",
  "pulled_and_pushed",
  "joined",
  "rolled_back",
]);

/** The newest round that reached the remote, for "no round has finished since". */
export function lastGoodRound(runs: SyncRound[]): SyncRound | null {
  return runs.find((r) => GOT_THROUGH.has(r.status)) ?? null;
}
