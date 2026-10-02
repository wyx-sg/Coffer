// src/lib/origin.ts — "return to where you came from" for detail pages.
//
// A link that opens a detail page from another page (an agent's Skills tab, a
// CLI's requirements, ...) passes the page it left in the router location
// state: `<Link to=... state={originState(location, "Claude Code")}>`. The
// detail page reads it with `useOrigin()` / `useBackTarget(fallback)` and its
// back link goes there, named for it ("← Back to Claude Code"). The state is a
// plain history entry, so the browser's Back works too and survives a reload.
// A page opened with no origin (a typed address, the sidebar) falls back to
// its own list.
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";

import { NAV_ENTRIES } from "@/lib/navigation";

export interface Origin {
  /** An in-app path (with search) to return to. */
  to: string;
  /** The page's name, shown as "Back to {label}". */
  label: string;
}

export interface OriginState {
  from: Origin;
}

/** The router `state` that names `location` as the page being left. */
export function originState(
  location: { pathname: string; search?: string },
  label: string,
): OriginState {
  return { from: { to: `${location.pathname}${location.search ?? ""}`, label } };
}

/** The origin out of a location state, or null when absent or not an in-app path. */
export function readOrigin(state: unknown): Origin | null {
  const from = (state as { from?: Partial<Origin> } | null | undefined)?.from;
  if (!from || typeof from.to !== "string" || typeof from.label !== "string") return null;
  if (!from.to.startsWith("/") || from.to.startsWith("//")) return null;
  return { to: from.to, label: from.label };
}

/** The origin this page was opened from, or null. */
export function useOrigin(): Origin | null {
  return readOrigin(useLocation().state);
}

/** The origin when there is one, else `fallback` (the page's own list). */
export function useBackTarget(fallback: Origin): Origin {
  return useOrigin() ?? fallback;
}

export interface BackLinkProps {
  to: string;
  label: string;
}

/** A header's back link: where the page was opened from ("Back to {origin}"),
 *  else `fallback` (the page's own parent, named by the page), else none. */
export function useBackLink(fallback: Origin): BackLinkProps;
export function useBackLink(fallback: Origin | undefined): BackLinkProps | undefined;
export function useBackLink(fallback: Origin | undefined): BackLinkProps | undefined {
  const { t } = useTranslation();
  const target = useOrigin() ?? fallback;
  return target ? { to: target.to, label: t("common.backTo", { label: target.label }) } : undefined;
}

/** `state` for a link opened from the current page, named `label`. */
export function useOriginState(label: string): OriginState {
  const { pathname, search } = useLocation();
  return originState({ pathname, search }, label);
}

/** `state` for a link opened from the current page, named by the sidebar page
 *  it belongs to ("Overview", "Activity", "Secrets", ...). Without a sidebar
 *  page (a path no entry owns) the state is omitted: the target falls back to
 *  its own list. */
export function useHereOriginState(): OriginState | undefined {
  const { t } = useTranslation();
  const { pathname, search } = useLocation();
  const entry = NAV_ENTRIES.find((e) =>
    e.to === "/" ? pathname === "/" : pathname === e.to || pathname.startsWith(`${e.to}/`),
  );
  return entry ? originState({ pathname, search }, t(entry.labelKey)) : undefined;
}
