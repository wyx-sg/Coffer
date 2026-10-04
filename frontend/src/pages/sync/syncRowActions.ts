// frontend/src/pages/sync/syncRowActions.ts
//
// Which rounds may be rolled back.
//
// Rollback names the round it undoes (`POST /sync/runs/{id}/rollback`), so any
// round can carry it — but only a round that left a snapshot and changed
// something here. A round that only pushed moved nothing on this machine, and
// "roll back" on a row that changed nothing offers to restore the state the
// vault is already in. A rollback is itself not rolled back: its snapshot is
// the state it already put back, and the daemon refuses it.
import type { SyncRound } from "@/lib/api/sync";

export function canRollBack(run: SyncRound): run is SyncRound & { id: number } {
  return (
    run.id !== null &&
    run.snapshot !== null &&
    run.applied.length > 0 &&
    run.status !== "rolled_back"
  );
}
