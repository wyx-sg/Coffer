// src/lib/secrets/listState.ts — the Secrets list's filter, sort and view, as the URL's query string (spec web-ui "Manage stored secrets on the Secrets page").
//
// Search text, status, owner type, sort and the list / by-owner view all live in the URL
// so a filtered list survives a reload and is a link. Defaults are never spelled out.

export const STATUSES = ["all", "inUse", "unused", "pending", "refused"] as const;
export type SecretStatus = (typeof STATUSES)[number];

/** What kind of thing owns a secret; `other` gathers every kind without its own filter entry. */
export const OWNER_KINDS = [
  "mcp_server",
  "channel",
  "provider",
  "sync",
  "custom_tool",
  "other",
] as const;
export type OwnerKind = (typeof OWNER_KINDS)[number];

export const SORT_KEYS = ["name", "usedBy", "lastUsed", "created"] as const;
export type SortKey = (typeof SORT_KEYS)[number];

export type SortDir = "asc" | "desc";
export type SecretView = "list" | "owner";

/** `sort: null` is the default order: waiting for approval first, then by name. */
export interface SecretListState {
  q: string;
  status: SecretStatus;
  kind: OwnerKind | "all";
  sort: SortKey | null;
  dir: SortDir;
  view: SecretView;
}

const pick = <T extends string>(allowed: readonly T[], raw: string | null, fallback: T): T =>
  allowed.includes(raw as T) ? (raw as T) : fallback;

/** The state a query string describes; `storedView` is the remembered view when the URL names none. */
export function parseListState(params: URLSearchParams, storedView: SecretView): SecretListState {
  const sort = params.get("sort");
  return {
    q: params.get("q") ?? "",
    status: pick(STATUSES, params.get("status"), "all"),
    kind: pick(["all", ...OWNER_KINDS] as const, params.get("kind"), "all"),
    sort: SORT_KEYS.includes(sort as SortKey) ? (sort as SortKey) : null,
    dir: params.get("dir") === "desc" ? "desc" : "asc",
    view: pick(["list", "owner"] as const, params.get("view"), storedView),
  };
}

/** The query string for `state`: only what differs from the defaults. `storedView` is what a URL
 *  naming no view reads back: a view other than the list is always written, and the list is
 *  written when the browser would otherwise open the other one. */
export function listStateParams(state: SecretListState, storedView: SecretView): URLSearchParams {
  const out = new URLSearchParams();
  if (state.q.trim()) out.set("q", state.q);
  if (state.status !== "all") out.set("status", state.status);
  if (state.kind !== "all") out.set("kind", state.kind);
  if (state.sort) {
    out.set("sort", state.sort);
    out.set("dir", state.dir);
  }
  if (state.view !== "list" || storedView !== "list") out.set("view", state.view);
  return out;
}

/** Whether any filter narrows the list (the sort and the view never do). */
export function isFiltered(state: SecretListState): boolean {
  return state.q.trim() !== "" || state.status !== "all" || state.kind !== "all";
}
