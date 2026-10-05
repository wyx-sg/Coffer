// src/components/SidebarNav.tsx — the sidebar's navigation: Overview, then the five groups and their rows.
// Layout owns the rail (width, collapse state, brand, search, footer); this
// file owns what goes in it — the entries of `lib/navigation.ts`, filtered by
// the experimental switches — and one row's rendering.
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, matchPath } from "react-router-dom";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { prefetchAllAgentSessions } from "@/lib/hooks/useAllAgentSessions";
import { isFeatureOn, useFeatureMap } from "@/lib/hooks/useFeatures";
import { NAV_GROUPS, type NavEntry } from "@/lib/navigation";
import { cn } from "@/lib/utils";

interface RowProps {
  entry: NavEntry;
  collapsed: boolean;
  active: boolean;
}

function NavRow({ entry, collapsed, active }: RowProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const label = t(entry.labelKey);
  // Hover or keyboard focus on Conversations warms its first page, so the page
  // opens on data already read (the cache keeps it fresh for 30s).
  const warm = entry.to === "/conversations" ? () => void prefetchAllAgentSessions(qc) : undefined;
  // An experimental feature's entry says so in the rail tooltip (the row
  // itself stays plain; the page's title carries the tag) — spec
  // experimental-features "Mark an experimental feature's sidebar entry".
  const experimental = entry.feature !== undefined;
  const link = (
    <Link
      to={entry.to}
      onPointerEnter={warm}
      onFocus={warm}
      aria-current={active ? "page" : undefined}
      aria-label={collapsed ? label : undefined}
      className={cn(
        "flex h-7 items-center rounded-item text-sm transition-colors duration-fast",
        collapsed ? "mx-auto w-8 justify-center" : "gap-[9px] px-2.5",
        active
          ? "bg-surface-selected font-label text-text"
          : "font-book text-text-muted hover:bg-surface-hover hover:text-text",
      )}
    >
      <entry.icon
        className={cn("size-[15px] shrink-0", active ? "text-accent" : "text-text-subtle")}
        strokeWidth={1.75}
        aria-hidden
      />
      {!collapsed ? <span className="flex-1 truncate">{label}</span> : null}
    </Link>
  );
  if (!collapsed) return link;
  // The rail has no room for the Experimental tag, so the tooltip carries it
  // after the name ("Knowledge · Experimental"; board 1.1.04). Otherwise the
  // tooltip is just the name: the sidebar carries no attention marks —
  // everything that needs the person is on Overview.
  const tip = experimental ? t("nav.experimentalLabel", { label }) : label;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{tip}</TooltipContent>
    </Tooltip>
  );
}

interface Props {
  collapsed: boolean;
  /** The path of the page the user is on — the one under the Settings modal
   *  while it is open, so opening Settings never un-marks the current page. */
  pathname: string;
}

export function SidebarNav({ collapsed, pathname }: Props) {
  const { t } = useTranslation();
  // An entry whose feature is off — or not known yet — is left out rather
  // than flashed in and taken away again.
  const features = useFeatureMap();
  const shown = (entry: NavEntry) => isFeatureOn(features, entry.feature);
  // Every entry matches by path prefix (segment-aware), so a detail page keeps
  // its list's entry marked: /agents/codex marks Agents. Overview is the index
  // and matches only itself.
  const isActive = (entry: NavEntry) =>
    matchPath({ path: entry.to, end: entry.to === "/" }, pathname) !== null;

  const groups = NAV_GROUPS.map((group) => ({ ...group, entries: group.entries.filter(shown) }))
    // A group whose every entry is left out leaves its heading out too, so no
    // heading stands over nothing.
    .filter((group) => group.entries.length > 0);

  return (
    <nav
      className="flex flex-1 flex-col gap-3.5 overflow-y-auto px-2.5 text-sm"
      aria-label={t("nav.aria.primary")}
    >
      {groups.map((group) => (
        // 14px between groups; inside one, 1px between rows on the sidebar and
        // 2px on the rail. The rail has no headings and no rules, only the gap.
        <div
          key={group.labelKey ?? "ungrouped"}
          className={cn("flex flex-col", collapsed ? "gap-0.5" : "gap-px")}
          role="group"
          aria-label={group.labelKey ? t(group.labelKey) : undefined}
        >
          {group.labelKey === null || collapsed ? null : (
            <div className="nav-group-label">{t(group.labelKey)}</div>
          )}
          {group.entries.map((entry) => (
            <NavRow key={entry.to} entry={entry} collapsed={collapsed} active={isActive(entry)} />
          ))}
        </div>
      ))}
    </nav>
  );
}
