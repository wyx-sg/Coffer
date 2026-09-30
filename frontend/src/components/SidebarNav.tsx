// src/components/SidebarNav.tsx — the sidebar's navigation: Overview, then the five groups and their rows.
// Layout owns the rail (width, collapse state, brand, search, footer); this
// file owns what goes in it — the entries of `lib/navigation.ts`, filtered by
// the experimental switches — and one row's rendering.
import { useTranslation } from "react-i18next";
import { Link, matchPath } from "react-router-dom";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { AttentionDot } from "@/components/shell/AttentionDot";
import { useAttentionSignals } from "@/lib/hooks/useAttentionSignals";
import { isFeatureOn, useFeatureMap } from "@/lib/hooks/useFeatures";
import { NAV_GROUPS, type NavEntry } from "@/lib/navigation";
import { cn } from "@/lib/utils";

interface RowProps {
  entry: NavEntry;
  collapsed: boolean;
  active: boolean;
  dot: boolean;
}

function NavRow({ entry, collapsed, active, dot }: RowProps) {
  const { t } = useTranslation();
  const label = t(entry.labelKey);
  // An experimental feature's entry says so, so nobody takes it for a
  // finished part of the product (spec experimental-features "Mark an
  // experimental feature's sidebar entry").
  const experimental = entry.feature !== undefined;
  const slug = entry.to === "/" ? "overview" : entry.to.replace(/\//g, "");
  const link = (
    <Link
      to={entry.to}
      aria-current={active ? "page" : undefined}
      aria-label={collapsed ? label : undefined}
      className={cn(
        "relative flex h-7 items-center rounded-item text-sm transition-colors duration-fast",
        collapsed ? "justify-center px-2" : "gap-[9px] px-2.5",
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
      {experimental && !collapsed ? (
        <span
          data-testid={`nav-experimental-${slug}`}
          className="shrink-0 rounded-xs border border-border px-1 text-[10px] font-normal leading-4 text-text-muted"
        >
          {t("nav.experimental")}
        </span>
      ) : null}
      {dot ? <AttentionDot entry={entry.to} collapsed={collapsed} /> : null}
    </Link>
  );
  if (!collapsed) return link;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">
        {experimental ? t("nav.experimentalLabel", { label }) : label}
      </TooltipContent>
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
  const signals = useAttentionSignals();
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
    <nav className="flex-1 overflow-y-auto px-2.5 pb-1 text-sm" aria-label={t("nav.aria.primary")}>
      {groups.map((group, i) => (
        <div
          key={group.labelKey ?? "ungrouped"}
          className="mb-1"
          role="group"
          aria-label={group.labelKey ? t(group.labelKey) : undefined}
        >
          {group.labelKey === null ? null : collapsed ? (
            i > 0 ? (
              <div className="mx-1 my-2 border-t border-border-subtle" />
            ) : null
          ) : (
            <div className="nav-group-label pt-3">{t(group.labelKey)}</div>
          )}
          {group.entries.map((entry) => (
            <NavRow
              key={entry.to}
              entry={entry}
              collapsed={collapsed}
              active={isActive(entry)}
              dot={signals[entry.to] === true}
            />
          ))}
        </div>
      ))}
    </nav>
  );
}
