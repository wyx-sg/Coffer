// src/lib/agents/owner.ts — who put an entry in the agent: Coffer, or the agent itself.
//
// The Skills, MCP servers, Plugins and Hooks tabs each list both in one table
// with one owner filter kept in the tab's URL as `?owner=coffer|own` (All is the
// bare address), spec agent-registry "Filter an agent's installed kinds by owner".
import { useSearchParamsKeepingState as useSearchParams } from "@/lib/hooks/useSearchParamsKeepingState";

export type Owner = "coffer" | "own";
export type OwnerFilter = "all" | Owner;

export const OWNER_FILTERS: readonly OwnerFilter[] = ["all", "coffer", "own"];

const PARAM = "owner";

export function parseOwnerFilter(value: string | null): OwnerFilter {
  return value === "coffer" || value === "own" ? value : "all";
}

/** The rows the filter keeps, in their order. */
export function filterByOwner<R extends { owner: Owner }>(
  rows: readonly R[],
  filter: OwnerFilter,
): R[] {
  return filter === "all" ? [...rows] : rows.filter((row) => row.owner === filter);
}

export interface OwnerCounts {
  coffer: number;
  own: number;
}

export function countByOwner(rows: readonly { owner: Owner }[]): OwnerCounts {
  let coffer = 0;
  for (const row of rows) if (row.owner === "coffer") coffer += 1;
  return { coffer, own: rows.length - coffer };
}

/** The tab's owner filter and its setter, kept in `?owner=` (other params survive). */
export function useOwnerFilter(): [OwnerFilter, (next: OwnerFilter) => void] {
  const [params, setParams] = useSearchParams();
  const filter = parseOwnerFilter(params.get(PARAM));
  const setFilter = (next: OwnerFilter) =>
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        if (next === "all") p.delete(PARAM);
        else p.set(PARAM, next);
        return p;
      },
      { replace: true },
    );
  return [filter, setFilter];
}
