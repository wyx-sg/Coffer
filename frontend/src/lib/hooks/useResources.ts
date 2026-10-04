// frontend/src/lib/hooks/useResources.ts
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { resourceListApi } from "@/lib/api/resourceList";
import { resourceKey, resourcesByKindKey } from "@/lib/api/queryKeys";
import type { Scope } from "@/lib/hooks/useScope";

export function useResources(kind?: string) {
  return useQuery({
    queryKey: resourcesByKindKey(kind),
    queryFn: () => resourceListApi.list(kind),
  });
}

/** One resource by uid. No kind argument: the uid names the row, and the row
 *  says what kind it is (`ResourceOut.kind`). */
export function useResource(uid: string) {
  return useQuery({
    queryKey: resourceKey(uid),
    queryFn: () => resourceListApi.get(uid),
    enabled: uid.length > 0,
  });
}

/** One resource's generic reach fields, as a table row needs them. */
/** @ui-only derived row view; never crosses the wire. */
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
