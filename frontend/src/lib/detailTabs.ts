// frontend/src/lib/detailTabs.ts — every detail page's tab lives in the path.
//
// A detail page is `/<kind>/<id>` for its default tab and `/<kind>/<id>/<tab>`
// for any other. This module owns that addressing so no page re-derives it:
// the open tab read from the `:tab` path segment, switching tab as a
// replace-navigation, and the fallback that sends an unknown `:tab` (or the
// default tab spelled out) to the bare default address. Search params (e.g.
// `?file=`) survive.
import { useEffect } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

/**
 * The address of a detail page on `tab`: `basePath` for the default tab (or an
 * unknown one), `${basePath}/${tab}` otherwise, followed by `search`.
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
  return `${basePath}${segment}${search}`;
}

/** Where an address whose path tab is `pathTab` must redirect to — the bare
 *  address, for a `:tab` that is unknown or the default — or `null` when the
 *  segment is already right. */
export function detailTabRedirect<T extends string>(
  basePath: string,
  pathTab: string | undefined,
  search: string,
  tabs: readonly T[],
  defaultTab: T,
): string | null {
  const segmentOk =
    pathTab === undefined ||
    (pathTab !== defaultTab && (tabs as readonly string[]).includes(pathTab));
  if (segmentOk) return null;
  return detailTabPath(basePath, pathTab, tabs, defaultTab, search);
}

/**
 * The open tab of a detail page and the setter that switches it.
 *
 * The tab is the route's optional `:tab` segment (unknown → `defaultTab`);
 * `setTab` replace-navigates to the address of the next tab, keeping the
 * search params. While `enabled`, an unknown or default `:tab` segment is
 * replaced by the bare address — a page whose subject has not resolved yet
 * passes `enabled: false`.
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

  const tab: T = (tabs as readonly string[]).includes(pathTab ?? "") ? (pathTab as T) : defaultTab;

  const redirect = enabled ? detailTabRedirect(basePath, pathTab, search, tabs, defaultTab) : null;
  useEffect(() => {
    if (redirect !== null) navigate(redirect, { replace: true });
  }, [redirect, navigate]);

  const setTab = (next: string) =>
    navigate(detailTabPath(basePath, next, tabs, defaultTab, search), { replace: true });

  return [tab, setTab];
}
