// frontend/src/lib/detailTabs.ts — every detail page's tab lives in the path.
//
// A detail page is `/<kind>/<id>` for its default tab and `/<kind>/<id>/<tab>`
// for any other, never `?tab=`. This module owns that addressing so no page
// re-derives it: the open tab read from the `:tab` path segment, switching tab
// as a replace-navigation, and the redirects that keep old addresses working —
// a `?tab=<tab>` query becomes the path form, and an unknown `:tab` falls back
// to the bare default address. Other search params (e.g. `?file=`) survive.
//
// Skills and MCP servers are addressed by NAME (fixed at creation, unique
// within the kind); `resolveByName` finds the row a `:name` segment names and
// reports when the segment was an old uid address that must redirect.
import { useEffect } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

/** `search` without its `tab` param, as a string with a leading `?` (or ""). */
function stripTab(search: string): string {
  const params = new URLSearchParams(search);
  params.delete("tab");
  const rest = params.toString();
  return rest ? `?${rest}` : "";
}

/**
 * The canonical address of a detail page on `tab`: `basePath` for the default
 * tab (or an unknown one), `${basePath}/${tab}` otherwise, followed by
 * `search` minus any `tab` param.
 */
export function detailTabPath<T extends string>(
  basePath: string,
  tab: string | null | undefined,
  tabs: readonly T[],
  defaultTab: T,
  search = "",
): string {
  const known = tab != null && (tabs as readonly string[]).includes(tab);
  const segment = known && tab !== defaultTab ? `/${encodeURIComponent(tab)}` : "";
  return `${basePath}${segment}${stripTab(search)}`;
}

/**
 * The canonical form of an address whose path tab is `pathTab` and whose query
 * is `search`, rebased on `basePath`. A legacy `?tab=` wins over the path
 * segment (it is the tab the old link asked for); a tab that is the default or
 * no known tab at all falls back to the bare address.
 */
export function canonicalDetailPath<T extends string>(
  basePath: string,
  pathTab: string | undefined,
  search: string,
  tabs: readonly T[],
  defaultTab: T,
): string {
  const queryTab = new URLSearchParams(search).get("tab");
  return detailTabPath(basePath, queryTab ?? pathTab, tabs, defaultTab, search);
}

/** Where the current address must redirect to (see `canonicalDetailPath`),
 *  or `null` when it is already canonical. */
export function detailTabRedirect<T extends string>(
  basePath: string,
  pathTab: string | undefined,
  search: string,
  tabs: readonly T[],
  defaultTab: T,
): string | null {
  const queryTab = new URLSearchParams(search).get("tab");
  const segmentOk =
    pathTab === undefined ||
    (pathTab !== defaultTab && (tabs as readonly string[]).includes(pathTab));
  if (queryTab === null && segmentOk) return null;
  return canonicalDetailPath(basePath, pathTab, search, tabs, defaultTab);
}

/**
 * The open tab of a detail page and the setter that switches it.
 *
 * The tab is the route's optional `:tab` segment (unknown → `defaultTab`);
 * `setTab` replace-navigates to the canonical address of the next tab, keeping
 * the other search params. While `enabled`, an address in a legacy or
 * non-canonical form is replaced by its canonical one — a page that is about
 * to redirect elsewhere (an old uid address) passes `enabled: false` so the two
 * redirects do not race.
 */
export function useDetailTab<T extends string>(
  tabs: readonly T[],
  defaultTab: T,
  basePath: string,
  { enabled = true }: { enabled?: boolean } = {},
): [T, (next: string) => void] {
  const { tab: pathTab } = useParams<{ tab?: string }>();
  const { search } = useLocation();
  const navigate = useNavigate();

  const queryTab = new URLSearchParams(search).get("tab");
  const wanted = queryTab ?? pathTab;
  const tab: T = (tabs as readonly string[]).includes(wanted ?? "") ? (wanted as T) : defaultTab;

  const redirect = enabled ? detailTabRedirect(basePath, pathTab, search, tabs, defaultTab) : null;
  useEffect(() => {
    if (redirect !== null) navigate(redirect, { replace: true });
  }, [redirect, navigate]);

  const setTab = (next: string) =>
    navigate(detailTabPath(basePath, next, tabs, defaultTab, search), { replace: true });

  return [tab, setTab];
}

/** What a `:name` segment resolved to: the row, and whether the segment was
 *  its uid (an old address that must redirect to the name). */
export interface NameMatch<R> {
  item: R;
  byUid: boolean;
}

/** Find the row a `:name` path segment names — by name first, then by uid
 *  (the addressing of old links). `null` when nothing matches. */
export function resolveByName<R extends { uid: string; name: string }>(
  items: readonly R[] | undefined,
  key: string,
): NameMatch<R> | null {
  if (!items || !key) return null;
  const byName = items.find((r) => r.name === key);
  if (byName) return { item: byName, byUid: false };
  const byUid = items.find((r) => r.uid === key);
  return byUid ? { item: byUid, byUid: true } : null;
}
