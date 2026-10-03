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

/** The prompt that hands files to an agent, and the files it covers. */
export type AgentHandoff = Schemas["AgentHandoffOut"];

/** Which files to hand over, and the agent / Coffer conversation they went to. */
export type HandoffRequest = Schemas["HandoffIn"];

/** What rolling a round back would put back, and what it leaves alone. */
export type RollbackPlan = Schemas["RollbackPlanOut"];

/** One row of the registry (`GET /sync/machines`). */
export type Machine = Schemas["MachineOut"];

export type MachineList = Schemas["MachineListOut"];

export type MachineRemoved = Schemas["MachineRemovedOut"];

/** `{ from, to }`: the folder the vault left (now empty) and the one it is in. */
export type VaultMoved = Schemas["VaultMoveOut"];

/** `DELETE /sync/remote` — whether a remote was forgotten, and whether Undo can put it back. */
export type SyncRemoteCleared = Schemas["SyncRemoteClearedOut"];

/** `GET`/`POST /sync/join-choices` — the files a join still has to answer. */
export type JoinChoices = Schemas["JoinChoicesOut"];

const api = () => getApiClient();

export const syncApi = {
  status: (): Promise<SyncStatus> => unwrap(api().GET("/sync/status")),
  /** One page of the rounds, newest first, read from `cursor` (null for the first). */
  runs: (
    { cursor, limit }: { cursor: string | null; limit: number },
    signal?: AbortSignal,
  ): Promise<SyncRunList> =>
    unwrap(
      api().GET("/sync/runs", {
        params: { query: { limit, cursor: cursor ?? undefined } },
        signal,
      }),
    ),
  run: (): Promise<SyncRound> => unwrap(api().POST("/sync/run")),

  putRemote: (remote: SyncRemoteInput): Promise<SyncRemote> =>
    unwrap(api().PUT("/sync/remote", { body: remote })),
  /** Stop syncing: forget the remote. The vault and its history stay. */
  clearRemote: (): Promise<SyncRemoteCleared> => unwrap(api().DELETE("/sync/remote")),
  /** Undo Stop syncing: the remote that was forgotten, and what this Mac knew about it. */
  restoreRemote: (): Promise<SyncRemote> => unwrap(api().POST("/sync/remote/restore")),
  /** Move the vault out of a synchronised folder: rounds and writes pause, the folder moves,
   *  its git repository is checked, then everything resumes. The old folder is left empty. */
  moveVault: (to: string): Promise<VaultMoved> =>
    unwrap(api().POST("/sync/vault/move", { body: { to } })),
  checkRemote: (body: RemoteCheckInput): Promise<RemoteCheck> =>
    unwrap(api().POST("/sync/remote/check", { body })),

  joinPreview: (): Promise<JoinPreview> => unwrap(api().GET("/sync/join/preview")),
  join: (): Promise<SyncRound> => unwrap(api().POST("/sync/join")),
  joinChoices: (): Promise<JoinChoices> => unwrap(api().GET("/sync/join-choices")),
  chooseJoin: (choices: JoinChoice[]): Promise<JoinChoices> =>
    unwrap(api().POST("/sync/join-choices", { body: { choices } })),
  /** The marked-up copy of a join's differing file, for Open in editor and for an agent. */
  joinEditorCopy: (path: string): Promise<EditorCopy> =>
    unwrap(api().POST("/sync/join-choices/editor", { body: { path } })),
  /** Hand a join's differing files (every one an agent may merge when `paths` is omitted) to an agent. */
  joinHandoff: (body: HandoffRequest = {}): Promise<AgentHandoff> =>
    unwrap(api().POST("/sync/join-choices/handoff", { body })),
  /** Back to two choices for one file: forgets the editor copy and any agent's merge. */
  discardJoinCopy: (path: string): Promise<JoinChoices> =>
    unwrap(api().POST("/sync/join-choices/discard", { body: { path } })),

  stop: (): Promise<StopState> => unwrap(api().GET("/sync/stop")),
  answerFile: (path: string, answer: ConflictAnswer): Promise<StopState> =>
    unwrap(api().POST("/sync/stop/files/answer", { body: { path, answer } })),
  /** Write a copy with conflict markers for the person to edit by hand. */
  editorCopy: (path: string): Promise<EditorCopy> =>
    unwrap(api().POST("/sync/stop/files/editor", { body: { path } })),
  fileVersions: (path: string): Promise<FileVersions> =>
    unwrap(api().GET("/sync/stop/files/versions", { params: { query: { path } } })),
  /**
   * Hand the stopped round's conflicting files to an agent (every file an agent may
   * merge when `paths` is omitted). Send it again with `agent` and `conversation_id`
   * once the conversation exists. The agent's merge shows as `agent_state:
   * "merged_by_agent"`; marking it resolved is `answerFile(path, "edited")`.
   */
  handoff: (body: HandoffRequest = {}): Promise<AgentHandoff> =>
    unwrap(api().POST("/sync/stop/handoff", { body })),
  /** Back to two choices for one file: forgets the editor copy, any agent's merge and its answer. */
  discardCopy: (path: string): Promise<StopState> =>
    unwrap(api().POST("/sync/stop/files/discard", { body: { path } })),
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
  /** Retire a machine now; `restoreMachine` is its Undo. */
  retire: (machineId: string): Promise<MachineRemoved> =>
    unwrap(
      api().DELETE("/sync/machines/{machine_id}", { params: { path: { machine_id: machineId } } }),
    ),
  /** Undo a retire: register the machine again with the descriptor it had. */
  restoreMachine: (machineId: string): Promise<Machine> =>
    unwrap(
      api().POST("/sync/machines/{machine_id}/restore", {
        params: { path: { machine_id: machineId } },
      }),
    ),
};
