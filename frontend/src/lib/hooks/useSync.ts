// frontend/src/lib/hooks/useSync.ts
//
// Vault export / import (spec vault-export-import): POST /sync/export, POST /sync/import, and
// the out-of-band master-key routes GET /sync/key/fingerprint + POST
// /sync/key/{export,import} — the latter two carry the key MATERIAL in the
// body, so the browser downloads/uploads a file itself rather than naming a
// host path for the daemon to write. A bundle stays an ordinary local
// directory the user carries to the other machine themselves.
//
// The backup half (GET|PUT /sync/remote, GET /sync/status, POST /sync/push)
// drives the one git remote exports are pushed to (spec vault-export-import
// ## Backup). Its payloads carry `credential_ref` — a name in the credential
// store — and never the push credential itself, so the remote is safe to
// render in a browser.
//
// Hand-written fetch, mirroring useEmbeddingConfig (the generated client only
// covers spec mcp-gateway).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";

/** One resource that could not be written/applied, with the reason why. */
export interface BundleFailure {
  ref: string;
  reason: string;
}

/**
 * The summary both operations report: how many items landed in each area
 * (knowledge/memory/skills/resources/state/credentials), which refs failed,
 * and the bundle directory the operation read or wrote.
 */
export interface BundleResult {
  path: string;
  counts: Record<string, number>;
  failures: BundleFailure[];
}

export interface KeyFingerprint {
  present: boolean;
  fingerprint: string | null;
}

function headers(extra: HeadersInit = {}): HeadersInit {
  return { "X-Coffer-Token": getCofferToken() ?? "", "X-Coffer-Actor": "ui", ...extra };
}

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const data = (await r.json().catch(() => null)) as {
      error?: { code?: string; message?: string; details?: unknown };
    } | null;
    throw new ApiError(
      data?.error?.code ?? "INTERNAL_ERROR",
      data?.error?.message ?? `request failed: ${r.status}`,
      data?.error?.details,
    );
  }
  return r;
}

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as T;
}

async function sendJson<T>(method: "POST" | "PUT", path: string, body: unknown): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method,
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await checkOk(r);
  return (await r.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  return sendJson<T>("POST", path, body);
}

async function putJson<T>(path: string, body: unknown): Promise<T> {
  return sendJson<T>("PUT", path, body);
}

/**
 * Write the vault into a bundle directory. Credentials (Fernet ciphertext,
 * never the master key) ride along only when `with_credentials` is set.
 */
export function useExportVault() {
  return useMutation({
    mutationFn: (args: { path: string; withCredentials: boolean }) =>
      postJson<BundleResult>("/sync/export", {
        path: args.path,
        with_credentials: args.withCredentials,
      }),
  });
}

/**
 * Apply a bundle directory back into this vault. The bundle wins per resource,
 * nothing is deleted, and per-resource failures come back in `failures`. An
 * import rewrites essentially the whole registry, so invalidate broadly.
 */
export function useImportVault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (path: string) => postJson<BundleResult>("/sync/import", { path }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
      void qc.invalidateQueries({ queryKey: ["agents"] });
      void qc.invalidateQueries({ queryKey: ["skills"] });
      // Imported ciphertext is only usable once this machine holds the key.
      void qc.invalidateQueries({ queryKey: ["sync-key-fingerprint"] });
    },
  });
}

export function useKeyFingerprint() {
  return useQuery({
    queryKey: ["sync-key-fingerprint"],
    queryFn: () => getJson<KeyFingerprint>("/sync/key/fingerprint"),
  });
}

/**
 * Install a key the user carried here as a FILE, read in the browser. The
 * material travels in the request body — the daemon never resolves a path the
 * page named, and the browser never has to learn one.
 */
export function useImportMasterKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (material: string) =>
      postJson<{ locked_refs: string[] }>("/sync/key/import", { material }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["sync-key-fingerprint"] });
    },
  });
}

/**
 * Hand this machine's key back to the page so it can be downloaded as a file.
 * The key crosses only the loopback origin the user is already authenticated
 * against; it is still never written into an export bundle.
 */
export function useExportMasterKey() {
  return useMutation({
    mutationFn: () => postJson<{ material: string }>("/sync/key/export", {}),
  });
}

// --- backup remote (spec vault-export-import ## Backup) ---------------------

/** How the daemon describes the one backup remote — its ref, never its secret. */
export interface BackupRemote {
  url: string;
  branch: string;
  /**
   * A name in Coffer's credential store. The daemon resolves it to a real
   * push credential at push time and nowhere else, so nothing on this page,
   * in a log, or in the mirrored repository ever holds the secret.
   */
  credential_ref: string | null;
  include_credentials: boolean;
  interval_seconds: number;
  enabled: boolean;
  worktree_path: string;
}

/** `GET /sync/remote`. `configured: false` (remote `null`) is the fresh-vault state. */
export interface BackupRemoteState {
  configured: boolean;
  remote: BackupRemote | null;
}

/** One run's outcome; `error` reaches us already scrubbed of any token. */
export interface BackupRun {
  status: string;
  commit: string | null;
  error: string | null;
  ran_at: string | null;
}

/** `GET /sync/status` — the remote plus its last run. */
export interface BackupStatus {
  configured: boolean;
  remote: BackupRemote | null;
  last_run: BackupRun | null;
}

export const BACKUP_REMOTE_KEY = ["sync-backup-remote"];
export const BACKUP_STATUS_KEY = ["sync-backup-status"];

/** The configured remote. Drives the form; `/status` drives the run report. */
export function useBackupRemote() {
  return useQuery({
    queryKey: BACKUP_REMOTE_KEY,
    queryFn: () => getJson<BackupRemoteState>("/sync/remote"),
  });
}

export function useBackupStatus() {
  return useQuery({
    queryKey: BACKUP_STATUS_KEY,
    queryFn: () => getJson<BackupStatus>("/sync/status"),
  });
}

/**
 * Store the remote, replacing any previous one — the card auto-saves, so this
 * fires on every edit the user finishes rather than behind a Save button.
 */
export function useSaveBackupRemote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (remote: Omit<BackupRemote, "worktree_path"> & { worktree_path?: string }) =>
      putJson<BackupRemote>("/sync/remote", remote),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: BACKUP_REMOTE_KEY });
      void qc.invalidateQueries({ queryKey: BACKUP_STATUS_KEY });
    },
  });
}

/**
 * Run one backup now. A run that could not push comes back as a 200 carrying
 * `push_failed` rather than an error: the commit is already safe locally and
 * the caller wants the run's story. Refreshes the status either way.
 */
export function useRunBackupNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => postJson<BackupRun>("/sync/push", {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: BACKUP_STATUS_KEY });
      void qc.invalidateQueries({ queryKey: BACKUP_REMOTE_KEY });
    },
  });
}
