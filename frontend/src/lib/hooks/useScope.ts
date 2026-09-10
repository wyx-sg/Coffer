// frontend/src/lib/hooks/useScope.ts
//
// Generic per-agent activation scope (ADR per-agent-resource-scope): any resource kind that opts in
// (today `mcp_server` and `skill`) exposes GET/PUT
// /resources/{kind}/{name}/scope via the framework-level resource_routes.py —
// not a per-kind endpoint. Hand-written fetch, mirroring useSync.ts (the
// generated client doesn't cover the /scope sub-routes yet).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { useToast } from "@/components/ui/toast";
import type { components } from "@/lib/api/types";

/**
 * A resource's activation scope: the list of agent names it is active for.
 * `null` (absent from this type — see `ResourceScope.scope`) means every
 * agent; `[]` means no agent, i.e. dormant.
 */
export type Scope = string[];

/**
 * GET .../scope response: the current scope (`null` = unscoped, active for
 * every agent) plus whether this kind supports scope at all
 * (`supports_scope: false` for `agent`, `channel`, `knowledge_base` and
 * `memory`, which reject a non-null value at validation).
 *
 * Field names here MUST match `ResourceScopeOut` in
 * `backend/coffer/surfaces/http/schemas.py` — these sub-routes are hand-written
 * (the generated client does not cover them), so nothing checks this at compile
 * time. `resourceScopeContract` below is the regression guard.
 */
export interface ResourceScope {
  scope: Scope | null;
  supports_scope: boolean;
}

type ResourceOut = components["schemas"]["ResourceOut"];

export function resourceScopeKey(kind: string, name: string) {
  return ["scope", kind, name] as const;
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

async function putJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method: "PUT",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await checkOk(r);
  return (await r.json()) as T;
}

function scopePath(kind: string, name: string): string {
  return `/resources/${encodeURIComponent(kind)}/${encodeURIComponent(name)}/scope`;
}

/** Current activation scope for one resource, plus whether its kind supports scope. */
export function useResourceScope(kind: string, name: string) {
  return useQuery({
    queryKey: resourceScopeKey(kind, name),
    queryFn: () => getJson<ResourceScope>(scopePath(kind, name)),
    enabled: name.length > 0,
  });
}

/**
 * Replace a resource's activation scope (`null` clears it back to unscoped —
 * active for every agent). A scope change flips what the gateway exposes and
 * what skill delivery reconciles, so the agent-facing lists are invalidated
 * alongside the scope itself.
 */
export function useUpdateResourceScope(kind: string, name: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (scope: Scope | null) => putJson<ResourceOut>(scopePath(kind, name), { scope }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: resourceScopeKey(kind, name) });
      void qc.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
