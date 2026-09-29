// frontend/src/lib/api/sync.ts — wire types + requests for /api/v1/sync/*
// (spec vault-sync). Every wire type is an alias of the vault-sync contract's
// generated schemas (`generated/vault-sync.ts`), which is generated from
// `backend/coffer/surfaces/http/sync_schemas.py`.
//
// `POST /sync/restore` is deliberately absent, and the absence is the honest
// answer rather than a gap: it takes a point in the REMOTE's history (a sha, a
// ref, or a date) and no route exposes that history, so a browser could only
// offer a blind date box. There is no preview of what would come back and no
// way to tell "that date holds nothing" from "the wrong date" — and the
// recovery it performs is asymmetric (it re-adds, never deletes), which is
// exactly the nuance a blind box cannot convey. Restoring stays `coffer sync
// restore`, where the user has `git log` on the working tree beside it. Undo
// (`/rollback`) has none of that trouble: it names no revision.
//
// Nothing here ever carries the push credential or the master key into a
// stored shape: a remote names its credential by REFERENCE, which the daemon
// resolves at push time and nowhere else, so a fully configured remote is safe
// to render in a browser. No route here returns the master key: a backup is
// written by the desktop shell after a presence check (`@/lib/tauri`). Import
// is the one transient exception — the material the user picked crosses the
// loopback origin in a request body, into the daemon, never back out.
import { call, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/vault-sync";

type Schemas = components["schemas"];

/** Per-round change counts for one direction of the diff. */
export type DiffCounts = Schemas["DiffCountsOut"];

/**
 * A round the deletion guard held.
 *
 * `direction` is the whole point: `apply` means the remote would delete too
 * much of THIS vault, `publish` means this vault would delete too much of the
 * REMOTE — the case where this machine is the damaged one and confirming would
 * take every other machine down with it.
 */
export type PendingConfirmation = Schemas["PendingConfirmationOut"];

/**
 * The outcomes a round can end in, taken from the generated contract rather
 * than restated. Every surface that decides something from a round's status
 * narrows this union, so a status renamed or added on the backend fails
 * `npm run typecheck` here instead of being silently carried by one surface.
 */
export type RoundStatus = Schemas["RoundOut"]["status"];

/** One converge round's outcome (`RoundOut`). */
export type ConvergeRound = Schemas["RoundOut"];

/**
 * One round as the HISTORY holds it (`RunRecordOut`) — the same report a
 * status round carries, plus when it ran and the id its row is keyed on.
 */
export type RunRecord = Schemas["RunRecordOut"];

/** `GET /sync/runs` — every round, newest first. */
export type SyncRunList = Schemas["SyncRunListOut"];

/**
 * The join `/adopt` would make, stated before anything is applied
 * (`GET /sync/join`). `joining: false` means this machine already converged
 * here and converging is an ordinary round; `case: "ambiguous"` is a returning
 * machine whose base is gone, which joins only on the explicit `keep-local`
 * choice.
 */
export type JoinPreview = Schemas["JoinPreviewOut"];

/** The one answer an ambiguous join takes. */
export type JoinChoice = "keep-local";

/** The one remote this vault converges with. `credential_ref` is a NAME. */
export type SyncRemote = Schemas["SyncRemoteOut"];

/** `GET /sync/status` — the remote, its last round, and this machine's id. */
export type SyncStatus = Schemas["SyncStatusOut"];

/** One row of the registry (`GET /sync/machines`). */
export type Machine = Schemas["MachineOut"];

export type MachineList = Schemas["MachineListOut"];

export type MachineRemoved = Schemas["MachineRemovedOut"];

/** The remote as it is written: every field but the URL carries a default. */
export type SyncRemoteInput = Schemas["SyncRemoteIn"];

export const syncApi = {
  putRemote: (remote: SyncRemoteInput) =>
    call<SyncRemote>("/sync/remote", { method: "PUT", body: remote }),
  status: () => call<SyncStatus>("/sync/status"),

  /** Every round this vault has run, newest first. Unfiltered on purpose:
   *  the rounds that changed nothing are what make a GAP in the record
   *  visible, and a history without them reads as an idle vault. */
  runs: (limit = 500) => call<SyncRunList>(`/sync/runs?limit=${limit}`),

  run: () => call<ConvergeRound>("/sync/run", { method: "POST" }),
  /** What joining would do, applying nothing. Asked before every join. */
  previewJoin: (choice?: JoinChoice) =>
    call<JoinPreview>(choice ? `/sync/join?choice=${enc(choice)}` : "/sync/join"),
  /** Join the remote — only after the preview has been shown. */
  adopt: (choice?: JoinChoice) =>
    call<ConvergeRound>("/sync/adopt", { method: "POST", body: choice ? { choice } : {} }),
  confirm: () => call<ConvergeRound>("/sync/confirm", { method: "POST" }),
  reject: () => call<{ cleared: boolean }>("/sync/reject", { method: "POST" }),
  /** Replace this vault with the remote's, discarding what only it holds.
   *  The third answer for a machine whose files are gone: confirming a held
   *  round would publish the loss, rejecting would refuse it forever. */
  rebuild: () => call<ConvergeRound>("/sync/rebuild", { method: "POST" }),
  /**
   * Undo the last applied round, from the pre-apply snapshot it left behind.
   *
   * Takes no argument on purpose: the daemon reverses the round that left the
   * NEWEST snapshot, so there is no round to name. A surface that offers this
   * has to point at that one round itself (`rollbackTargetId`) rather than
   * letting a user pick — every other choice would run this same call.
   *
   * 409 `SYNC_NOTHING_TO_ROLL_BACK` when no snapshot survives: the pruning
   * keeps ten, and a vault with no remote has none.
   */
  rollback: () => call<ConvergeRound>("/sync/rollback", { method: "POST" }),

  machines: () => call<MachineList>("/sync/machines"),
  renameSelf: (name: string) =>
    call<Machine>("/sync/machines/self", { method: "PATCH", body: { name } }),
  retire: (machineId: string) =>
    call<MachineRemoved>(`/sync/machines/${enc(machineId)}`, { method: "DELETE" }),

  keyFingerprint: () => call<{ fingerprint: string | null }>("/sync/key/fingerprint"),
  importKey: (material: string) =>
    call<{ locked_refs: string[] }>("/sync/key/import", { method: "POST", body: { material } }),
};
