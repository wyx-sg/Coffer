// frontend/src/lib/hooks/useMachines.ts
//
// The Machines fleet view (spec 010 amendment, ADR-045): GET /machines lists
// the synced machine registry — byte-identical wire shape to GET
// /sync/machines (both build on sync_routes.machines_out), just surfaced
// under its own top-level path since the frontend Machines nav item is not
// really "sync configuration" (see backend/coffer/surfaces/http/
// machines_routes.py). GET /machines/{id}/slice renders one machine's
// computed activation slice — which agents/mcp_servers/skills/channels are
// active on it, derived from each resource's scope (ADR-045) — intent only,
// no local FS/process checks. Hand-written fetch, mirroring useSync.ts (the
// generated client only covers spec 001).
import { useQuery } from "@tanstack/react-query";

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";
import type { SyncMachine } from "@/lib/hooks/useSync";

export type { SyncMachine };

/**
 * One entry in a machine's activation slice: an agent, mcp_server, skill, or
 * channel, and whether it's active on this machine. `agents` narrows further
 * by which bound agents it's active for — present only on the mcp_server and
 * skill axes (DualAxisSliceOut on the backend); absent for the agent and
 * channel axes, which don't narrow by agent.
 */
export interface SliceEntry {
  name: string;
  active: boolean;
  agents?: string[];
}

/** GET /machines/{id}/slice response (MachineSliceOut on the backend). */
export interface MachineSlice {
  machine: SyncMachine;
  agents: SliceEntry[];
  mcp_servers: SliceEntry[];
  skills: SliceEntry[];
  channels: SliceEntry[];
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

/** The full synced machine registry (spec 010) — which machines exist, and which is local. */
export function useMachines() {
  return useQuery({
    queryKey: ["machines"],
    queryFn: () => getJson<{ machines: SyncMachine[] }>("/machines"),
  });
}

/** One machine's computed activation slice (what's active on it, intent only). */
export function useMachineSlice(id: string) {
  return useQuery({
    queryKey: ["machines", id, "slice"],
    queryFn: () => getJson<MachineSlice>(`/machines/${encodeURIComponent(id)}/slice`),
    enabled: id.length > 0,
  });
}
