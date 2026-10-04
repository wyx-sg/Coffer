// src/lib/secrets/listState.ts — the Secrets list's filter, as the URL's query string (spec web-ui "Manage stored secrets on the Secrets page").
//
// Search text and status live in the URL so a filtered list survives a reload and is a link.
// Defaults are never spelled out. The sort is the shared `?sort=` (useSortParam), not part of this.

export const STATUSES = ["all", "inUse", "unused"] as const;
export type SecretStatus = (typeof STATUSES)[number];

export interface SecretListState {
  q: string;
  status: SecretStatus;
}

/** The state a query string describes. */
export function parseListState(params: URLSearchParams): SecretListState {
  const status = params.get("status");
  return {
    q: params.get("q") ?? "",
    status: STATUSES.includes(status as SecretStatus) ? (status as SecretStatus) : "all",
  };
}

/** `prev` with the filter keys rewritten for `state`: only what differs from the defaults. */
export function withListState(prev: URLSearchParams, state: SecretListState): URLSearchParams {
  const out = new URLSearchParams(prev);
  if (state.q.trim()) out.set("q", state.q);
  else out.delete("q");
  if (state.status !== "all") out.set("status", state.status);
  else out.delete("status");
  return out;
}
