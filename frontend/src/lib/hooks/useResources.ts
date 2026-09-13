// frontend/src/lib/hooks/useResources.ts
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import type { Scope } from "@/lib/hooks/useScope";

type ResourceOut = components["schemas"]["ResourceOut"];

export function useResources(kind?: string) {
  return useQuery({
    queryKey: ["resources", { kind }],
    queryFn: async (): Promise<ResourceOut[]> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/resources", {
        params: { query: kind ? { kind } : {} },
      });
      if (error)
        throwApiError(error, "INTERNAL_ERROR", `failed to list resources: ${kind ?? "all"}`);
      return data?.resources ?? [];
    },
  });
}

export function useResource(kind: string, name: string) {
  return useQuery({
    queryKey: ["resources", kind, name],
    queryFn: async (): Promise<ResourceOut> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/resources/{kind}/{name}", {
        params: { path: { kind, name } },
      });
      if (error) throwApiError(error, "RESOURCE_NOT_FOUND", "resource not found");
      if (!data) throw new ApiError("RESOURCE_NOT_FOUND", "empty resource response");
      return data;
    },
  });
}

/** One resource's generic reach fields, as a table row needs them. */
export interface ResourceReach {
  enabled: boolean;
  scope: Scope | null;
}

/**
 * `name → {enabled, scope}` for one kind.
 *
 * Some kinds are listed through a DEDICATED endpoint that carries only what is
 * read off disk (`/knowledge/collections`, `/providers`, `/memory/partitions`)
 * — `enabled` and `scope` are generic Resource fields and are not on it. A
 * table rendering the reach control per row therefore merges them in from
 * `GET /resources?kind=…`: ONE extra request for the whole table, never one per
 * row, which is the same bargain the mcp-servers and skills lists strike by
 * carrying `scope` on their own row payload.
 */
export function useKindReach(kind: string): Map<string, ResourceReach> {
  const { data } = useResources(kind);
  return useMemo(
    () =>
      new Map(
        (data ?? []).map((r) => [r.name, { enabled: r.enabled, scope: r.scope ?? null }] as const),
      ),
    [data],
  );
}
