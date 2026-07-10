// frontend/src/lib/hooks/useSync.ts
//
// Multi-machine sync (spec 010): GET/PUT /sync/config, GET /sync/status, and
// POST /sync/{run,resolve,key/import,key/export}. Hand-written fetch, mirroring
// useEmbeddingConfig (the generated client only covers spec 001).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";

export interface SyncConfig {
  remote: string | null;
  enabled: boolean;
  auto: boolean;
  interval_seconds: number;
  poll_remote_seconds: number;
  branch: string;
  updated_at?: string;
}

export interface SyncStatus {
  status: "unconfigured" | "clean" | "syncing" | "conflicted" | "error" | "credentials_locked";
  last_sync_at: string | null;
  last_error: string | null;
  /** Actionable classification of last_error: auth | not_found | network. */
  error_hint: string | null;
  conflict_paths: string[];
  locked_refs: string[];
  quarantined_refs: string[];
}

export interface KeyFingerprint {
  present: boolean;
  fingerprint: string | null;
}

export interface SyncMachine {
  machine_id: string;
  display_name: string;
  platform: string | null;
  os_version: string | null;
  coffer_version: string | null;
  last_sync_at: string | null;
  is_local: boolean;
}

function headers(extra: HeadersInit = {}): HeadersInit {
  return { "X-Coffer-Token": getCofferToken() ?? "", "X-Coffer-Actor": "ui", ...extra };
}

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const data = (await r.json().catch(() => null)) as {
      error?: { code?: string; message?: string; details?: unknown };
    } | null;
    // details carries the actionable hint of SYNC_REMOTE_UNREACHABLE
    // (auth/not_found/network) — the save-failure UI renders guidance from it.
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

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await checkOk(r);
  return (await r.json()) as T;
}

export function useSyncConfig() {
  return useQuery({
    queryKey: ["sync-config"],
    queryFn: () => getJson<SyncConfig>("/sync/config"),
  });
}

export function useSyncStatus() {
  return useQuery({
    queryKey: ["sync-status"],
    queryFn: () => getJson<SyncStatus>("/sync/status"),
  });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["sync-config"] });
    void qc.invalidateQueries({ queryKey: ["sync-status"] });
    // A run rewrites this machine's registry entry (last-sync time).
    void qc.invalidateQueries({ queryKey: ["sync-machines"] });
    // A key import changes the fingerprint the user compares across machines.
    void qc.invalidateQueries({ queryKey: ["sync-key-fingerprint"] });
  };
}

export function useUpdateSyncConfig() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (body: SyncConfig) => {
      const r = await fetch(`${getCofferBaseUrl()}/sync/config`, {
        method: "PUT",
        headers: { ...headers(), "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      await checkOk(r);
      return (await r.json()) as SyncConfig;
    },
    onSuccess: invalidate,
  });
}

export function useRunSync() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => postJson<SyncStatus>("/sync/run", {}),
    onSuccess: invalidate,
  });
}

export function useKeyFingerprint() {
  return useQuery({
    queryKey: ["sync-key-fingerprint"],
    queryFn: () => getJson<KeyFingerprint>("/sync/key/fingerprint"),
  });
}

export function useSyncMachines() {
  return useQuery({
    queryKey: ["sync-machines"],
    queryFn: () => getJson<{ machines: SyncMachine[] }>("/sync/machines"),
  });
}

export function useRenameMachine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (display_name: string) => {
      const r = await fetch(`${getCofferBaseUrl()}/sync/machine`, {
        method: "PUT",
        headers: { ...headers(), "Content-Type": "application/json" },
        body: JSON.stringify({ display_name }),
      });
      await checkOk(r);
      return (await r.json()) as SyncMachine;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["sync-machines"] });
    },
  });
}

export function useImportMasterKey() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (path: string) => postJson<SyncStatus>("/sync/key/import", { path }),
    onSuccess: invalidate,
  });
}

export function useExportMasterKey() {
  return useMutation({
    mutationFn: (path: string) => postJson<{ path: string }>("/sync/key/export", { path }),
  });
}
