// frontend/src/lib/api/sync.ts — wire types + requests for /api/v1/sync/*
// (spec vault-sync). Every wire type is an alias of the vault-sync contract's
// generated schemas (`generated/vault-sync.ts`), generated from
// `backend/coffer/surfaces/http/sync_schemas.py` and `sync_stop_schemas.py`.
//
// Sync is thin: a round fetches, merges with git, and stops for a person on
// anything it cannot decide alone — a conflicting file, a large deletion, a
// join that finds differing files. Each of those has its own routes here, and
// each answers the one situation the daemon is holding rather than a round
// named in the request, except rollback, which names the round it undoes.
//
// Nothing here ever carries the push secret or the master key into a
// stored shape: a remote names its secret by REFERENCE, which the daemon
// resolves at push time and nowhere else, so a fully configured remote is safe
// to render in a browser. Import is the one transient exception — the material
// the user picked crosses the loopback origin in a request body, into the
// daemon, never back out.
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/vault-sync";

type Schemas = components["schemas"];

/**
 * The outcomes a round can end in, from the generated contract rather than
 * restated, so a status renamed or added on the backend fails typecheck in
 * every surface that decides something from it.
 */
export type RoundStatus = Schemas["RoundStatus"];

/** One round's report (`RoundOut`), from a status, the history or an action. */
export type SyncRound = Schemas["RoundOut"];

/** One file a round changed, in one direction. */
export type SyncChange = Schemas["SyncChangeOut"];

/** `GET /sync/runs` — rounds, newest first. */
export type SyncRunList = Schemas["SyncRunListOut"];

/** `GET /sync/status` — the remote, the last round, what waits, what is wrong. */
export type SyncStatus = Schemas["SyncStatusOut"];

/** One local commit the remote does not have yet. */
export type WaitingCommit = Schemas["WaitingCommitOut"];

/** Why sync is not working right now, when it is not. */
export type SyncProblem = Schemas["ProblemOut"];

/** The one remote this vault syncs with. `secret_ref` is a NAME. */
export type SyncRemote = Schemas["SyncRemoteOut"];

/** The remote as it is written: every field but the URL carries a default. */
export type SyncRemoteInput = Schemas["SyncRemoteIn"];

export type RemoteCheckInput = Schemas["RemoteCheckIn"];

/** What a repository holds, asked before it is saved as the remote. */
export type RemoteCheck = Schemas["RemoteCheckOut"];

/** What joining would do, stated before anything is applied. */
export type JoinPreview = Schemas["JoinPreviewOut"];

/** A file a stopped round (or a join) left for a person to answer. */
export type ConflictFile = Schemas["ConflictFileOut"];

export type ConflictAnswer = Schemas["Answer"];

export type JoinChoice = Schemas["JoinChoiceIn"];

/** `GET /sync/stop` — whether a round is stopped, and on what. */
export type StopState = Schemas["StopStateOut"];

export type StoppedRound = Schemas["StoppedRoundOut"];

/** The deletion breaker's hold on a stopped round. */
export type SyncHold = Schemas["HoldOut"];

/** Both sides of one conflicting file, and what taking theirs changes. */
export type FileVersions = Schemas["FileVersionsOut"];

export type EditorCopy = Schemas["EditorCopyOut"];

/** What rolling a round back would put back, and what it leaves alone. */
export type RollbackPlan = Schemas["RollbackPlanOut"];

/** One row of the registry (`GET /sync/machines`). */
export type Machine = Schemas["MachineOut"];

export type MachineList = Schemas["MachineListOut"];

export type MachineRemoved = Schemas["MachineRemovedOut"];

/** `DELETE /sync/remote` — whether a remote was forgotten. */
export type SyncRemoteCleared = Schemas["SyncRemoteClearedOut"];

/** `GET`/`POST /sync/join-choices` — the files a join still has to answer. */
export type JoinChoices = Schemas["JoinChoicesOut"];

const api = () => getApiClient();

export const syncApi = {
  status: (): Promise<SyncStatus> => unwrap(api().GET("/sync/status")),
  runs: (limit = 500): Promise<SyncRunList> =>
    unwrap(api().GET("/sync/runs", { params: { query: { limit } } })),
  run: (): Promise<SyncRound> => unwrap(api().POST("/sync/run")),

  putRemote: (remote: SyncRemoteInput): Promise<SyncRemote> =>
    unwrap(api().PUT("/sync/remote", { body: remote })),
  /** Stop syncing: forget the remote. The vault and its history stay. */
  clearRemote: (): Promise<SyncRemoteCleared> => unwrap(api().DELETE("/sync/remote")),
  checkRemote: (body: RemoteCheckInput): Promise<RemoteCheck> =>
    unwrap(api().POST("/sync/remote/check", { body })),

  joinPreview: (): Promise<JoinPreview> => unwrap(api().GET("/sync/join/preview")),
  join: (): Promise<SyncRound> => unwrap(api().POST("/sync/join")),
  joinChoices: (): Promise<JoinChoices> => unwrap(api().GET("/sync/join-choices")),
  chooseJoin: (choices: JoinChoice[]): Promise<JoinChoices> =>
    unwrap(api().POST("/sync/join-choices", { body: { choices } })),

  stop: (): Promise<StopState> => unwrap(api().GET("/sync/stop")),
  answerFile: (path: string, answer: ConflictAnswer): Promise<StopState> =>
    unwrap(api().POST("/sync/stop/files/answer", { body: { path, answer } })),
  /** Write a copy with conflict markers for the person to edit by hand. */
  editorCopy: (path: string): Promise<EditorCopy> =>
    unwrap(api().POST("/sync/stop/files/editor", { body: { path } })),
  fileVersions: (path: string): Promise<FileVersions> =>
    unwrap(api().GET("/sync/stop/files/versions", { params: { query: { path } } })),
  /** "I merged it": every agent-mergeable file takes its saved copy as its answer. */
  markMerged: (): Promise<StopState> => unwrap(api().POST("/sync/stop/merged")),
  continueRound: (): Promise<SyncRound> => unwrap(api().POST("/sync/continue")),
  confirmHold: (): Promise<SyncRound> => unwrap(api().POST("/sync/hold/confirm")),
  restoreHold: (): Promise<SyncRound> => unwrap(api().POST("/sync/hold/restore")),
  /** "I checked it, push anyway" for a round that found a plaintext secret. */
  pushAnyway: (): Promise<SyncRound> => unwrap(api().POST("/sync/plaintext/push-anyway")),

  rollbackPlan: (runId: number): Promise<RollbackPlan> =>
    unwrap(api().GET("/sync/runs/{run_id}/rollback-plan", { params: { path: { run_id: runId } } })),
  rollback: (runId: number): Promise<SyncRound> =>
    unwrap(api().POST("/sync/runs/{run_id}/rollback", { params: { path: { run_id: runId } } })),

  machines: (): Promise<MachineList> => unwrap(api().GET("/sync/machines")),
  renameSelf: (name: string): Promise<Machine> =>
    unwrap(api().PATCH("/sync/machines/self", { body: { name } })),
  retire: (machineId: string): Promise<MachineRemoved> =>
    unwrap(
      api().DELETE("/sync/machines/{machine_id}", { params: { path: { machine_id: machineId } } }),
    ),
};
