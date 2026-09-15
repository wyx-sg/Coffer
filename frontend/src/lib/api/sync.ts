// frontend/src/lib/api/sync.ts — wire types + requests for /api/v1/sync/*
// (spec vault-sync). Mirrors `backend/coffer/surfaces/http/sync_schemas.py`,
// which is the authoritative contract. The vault-sync OpenAPI contract
// (`generated/vault-sync.ts`) lags it — no `/sync/runs`, a different `RoundOut`
// (`applied` as a path list, no `published`/`agent_resolved`/`locked_refs`),
// `MachineOut.last_converged_at` where the backend sends `last_converged_on` —
// so only the shapes the two agree on (the remote, a path failure) are aliased
// to it; the rest stay hand-written and must be kept in step by hand.
//
// Nothing here ever carries the push credential or the master key into a
// stored shape: a remote names its credential by REFERENCE, which the daemon
// resolves at push time and nowhere else, so a fully configured remote is safe
// to render in a browser. The key routes are the one exception and they are
// deliberately transient — the material crosses the loopback origin in a
// request body and the page hands it straight to a download or a file input.
import { call, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/vault-sync";

type Schemas = components["schemas"];

/** Per-round change counts for one direction of the diff. */
export interface DiffCounts {
  added: number;
  modified: number;
  deleted: number;
}

/** One path the round could not apply here, with the reason why. */
export type RoundFailure = Schemas["PathFailureOut"];

/** One area whose deletion share tripped the circuit breaker. */
export interface GuardBreach {
  area: string;
  deleted: number;
  total: number;
}

/**
 * A round the deletion guard held.
 *
 * `direction` is the whole point: `apply` means the remote would delete too
 * much of THIS vault, `publish` means this vault would delete too much of the
 * REMOTE — the case where this machine is the damaged one and confirming would
 * take every other machine down with it.
 */
export interface PendingConfirmation {
  direction: "apply" | "publish";
  breaches: GuardBreach[];
  paths: string[];
  raised_at: string;
}

/** One converge round's outcome (`RoundOut`). */
export interface ConvergeRound {
  status: string;
  /** `new` or `returning` when this round joined a remote; null otherwise. */
  join: "new" | "returning" | null;
  applied: DiffCounts;
  published: DiffCounts;
  commit: string | null;
  conflicts: string[];
  /** Paths an agent merged — reported whether or not the round succeeded. */
  agent_resolved: string[];
  failures: RoundFailure[];
  locked_refs: string[];
  pending: PendingConfirmation | null;
  error: string | null;
}

/**
 * One round as the HISTORY holds it (`RunRecordOut`) — the same report a
 * status round carries, plus when it ran and the id its row is keyed on.
 */
export interface RunRecord extends ConvergeRound {
  id: number;
  started_at: string;
  finished_at: string;
}

/** `GET /sync/runs` — every round, newest first. */
export interface SyncRunList {
  runs: RunRecord[];
}

/** The one remote this vault converges with. `credential_ref` is a NAME. */
export type SyncRemote = Schemas["SyncRemoteOut"];

/** `GET /sync/remote`. `configured: false` (remote null) is the fresh vault. */
export type SyncRemoteState = Schemas["SyncRemoteStateOut"];

/** `GET /sync/status` — the remote, its last round, and this machine's id. */
export interface SyncStatus {
  configured: boolean;
  remote: SyncRemote | null;
  last_run: ConvergeRound | null;
  machine_id: string;
  /** False when the id came from the local fallback file rather than the host,
   *  which means it does not survive deleting `~/.coffer`. */
  machine_id_is_derived: boolean;
}

/** One row of the registry (`GET /sync/machines`). */
export interface Machine {
  machine_id: string;
  name: string;
  os: string;
  hostname: string;
  coffer_version: string;
  /** The DAY this machine last converged — an idle machine deliberately does
   *  not stamp every round, so this is never an instant. */
  last_converged_on: string | null;
  /** Null when either side has published no fingerprint yet; false means that
   *  machine's credentials cannot be decrypted here. */
  key_matches: boolean | null;
  agents: string[];
  is_self: boolean;
}

export interface MachineList {
  machines: Machine[];
}

export interface MachineRemoved {
  removed: boolean;
}

/** The remote as it is written: every field but the URL carries a default. */
export type SyncRemoteInput = Omit<SyncRemote, "worktree_path"> & { worktree_path?: string };

export const syncApi = {
  getRemote: () => call<SyncRemoteState>("/sync/remote"),
  putRemote: (remote: SyncRemoteInput) =>
    call<SyncRemote>("/sync/remote", { method: "PUT", body: remote }),
  clearRemote: () => call<{ cleared: boolean }>("/sync/remote", { method: "DELETE" }),
  status: () => call<SyncStatus>("/sync/status"),

  /** Every round this vault has run, newest first. Unfiltered on purpose:
   *  the rounds that changed nothing are what make a GAP in the record
   *  visible, and a history without them reads as an idle vault. */
  runs: (limit = 500) => call<SyncRunList>(`/sync/runs?limit=${limit}`),

  run: () => call<ConvergeRound>("/sync/run", { method: "POST" }),
  confirm: () => call<ConvergeRound>("/sync/confirm", { method: "POST" }),
  reject: () => call<{ cleared: boolean }>("/sync/reject", { method: "POST" }),
  /** Replace this vault with the remote's, discarding what only it holds.
   *  The third answer for a machine whose files are gone: confirming a held
   *  round would publish the loss, rejecting would refuse it forever. */
  rebuild: () => call<ConvergeRound>("/sync/rebuild", { method: "POST" }),
  rollback: () => call<ConvergeRound>("/sync/rollback", { method: "POST" }),

  machines: () => call<MachineList>("/sync/machines"),
  renameSelf: (name: string) =>
    call<Machine>("/sync/machines/self", { method: "PATCH", body: { name } }),
  retire: (machineId: string) =>
    call<MachineRemoved>(`/sync/machines/${enc(machineId)}`, { method: "DELETE" }),

  keyFingerprint: () => call<{ fingerprint: string | null }>("/sync/key/fingerprint"),
  exportKey: () => call<{ material: string }>("/sync/key/export", { method: "POST" }),
  importKey: (material: string) =>
    call<{ locked_refs: string[] }>("/sync/key/import", { method: "POST", body: { material } }),
};
