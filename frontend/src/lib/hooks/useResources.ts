// frontend/src/lib/hooks/useResources.ts
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import { resourceKey, resourcesByKindKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";
import type { Scope } from "@/lib/hooks/useScope";

type ResourceOut = components["schemas"]["ResourceOut"];

export function useResources(kind?: string) {
  return useQuery({
    queryKey: resourcesByKindKey(kind),
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

/** One resource by uid. No kind argument: the uid names the row, and the row
 *  says what kind it is (`ResourceOut.kind`). */
export function useResource(uid: string) {
  return useQuery({
    queryKey: resourceKey(uid),
    queryFn: async (): Promise<ResourceOut> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/resources/{uid}", {
        params: { path: { uid } },
      });
      if (error) throwApiError(error, "RESOURCE_NOT_FOUND", "resource not found");
      if (!data) throw new ApiError("RESOURCE_NOT_FOUND", "empty resource response");
      return data;
    },
    enabled: uid.length > 0,
  });
}

/** One resource's generic reach fields, as a table row needs them. */
export interface ResourceReach {
  enabled: boolean;
  scope: Scope | null;
}

/**
 * `uid → {enabled, scope}` for one kind.
 *
 * Some kinds are listed through a DEDICATED endpoint that carries only what is
 * read off disk (`/knowledge/collections`, `/providers`, `/memory/partitions`)
 * — `enabled` and `scope` are generic Resource fields and are not on it. A
 * table rendering the reach control per row therefore merges them in from
 * `GET /resources?kind=…`: ONE extra request for the whole table, never one per
 * row, which is the same bargain the mcp-servers and skills lists strike by
 * carrying `scope` on their own row payload.
 *
 * Keyed on the uid, which every one of those dedicated payloads now carries:
 * keying on the name would make the join depend on two lists having been read
 * at the same instant, and a rename between them would silently drop a row's
 * reach back to its default.
 */
export function useKindReach(kind: string): Map<string, ResourceReach> {
  const { data } = useResources(kind);
  return useMemo(
    () =>
      new Map(
        (data ?? []).map((r) => [r.uid, { enabled: r.enabled, scope: r.scope ?? null }] as const),
      ),
    [data],
  );
}
