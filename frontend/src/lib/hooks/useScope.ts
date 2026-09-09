// frontend/src/lib/hooks/useScope.ts
//
// Generic machine x agent activation scope (ADR-045): any resource kind that
// opts in (Kind.scope_axes) exposes GET/PUT /resources/{kind}/{name}/scope
// via the framework-level resource_routes.py (Task 7) — not a per-kind
// endpoint. This is the shared mechanism kind-specific scope hooks should
// delegate to (see useChannels.ts's useChannelScope/useUpdateChannelScope,
// which used to own a private copy of this fetch logic before it existed).
// Hand-written fetch, mirroring useSync.ts (the generated client doesn't
// cover the /scope sub-routes yet).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { useToast } from "@/components/ui/toast";
import type { components } from "@/lib/api/types";

/**
 * A resource's machine x agent activation map. Keys are machine ids; each
 * value is `"*"` (active on that machine for every agent) or a list of agent
 * names (active on that machine only for those agents).
 */
export type Scope = Record<string, string[] | "*">;

/**
 * GET .../scope response: the current scope (`null` = unscoped, visible
 * everywhere) plus which axes this kind supports (empty axes means the kind
 * doesn't support scope at all).
 */
export interface ResourceScope {
  scope: Scope | null;
  axes: string[];
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

/** Current activation scope for one resource, plus the axes its kind supports. */
export function useResourceScope(kind: string, name: string) {
  return useQuery({
    queryKey: resourceScopeKey(kind, name),
    queryFn: () => getJson<ResourceScope>(scopePath(kind, name)),
    enabled: name.length > 0,
  });
}

/**
 * Replace a resource's activation scope (`null` clears it back to unscoped).
 * Invalidates the scope itself and `["machines"]` — a scope change can flip
 * what's active on any machine's fleet-view slice.
 */
export function useUpdateResourceScope(kind: string, name: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (scope: Scope | null) => putJson<ResourceOut>(scopePath(kind, name), { scope }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: resourceScopeKey(kind, name) });
      void qc.invalidateQueries({ queryKey: ["machines"] });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
