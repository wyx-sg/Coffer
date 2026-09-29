// src/components/Layout.tsx — the app shell: sidebar rail + the page, with the Settings modal and the command palette over it.
//
// The shell renders the page through `pageRoutes` against the location of the
// page the user is on, and `settingsRoutes` over it while a Settings route is
// open (spec web-ui "Open Settings as a modal from the sidebar footer"): the
// page underneath stays mounted, unchanged, and a fresh load of
// `/settings/<tab>` puts Overview under the modal.
//
// The rail is always present. At md+ it expands to a labelled sidebar whose
// width the user drags between 200 and 300px (spec web-ui "Resize every split
// view by its divider"), and collapses to a 56px icon rail (the choice persists
// in localStorage); below md it is always the icon rail, so narrow viewports
// keep their navigation. Collapsed rows get a tooltip and the language switcher
// folds into a globe popover.
import { useState } from "react";
import { Link, useLocation, useRoutes, type RouteObject } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useMediaQuery } from "@/lib/hooks/useMediaQuery";
import { useResizableWidth } from "@/lib/hooks/useResizableWidth";
import { isSettingsPath } from "@/lib/navigation";
import { useOpenSettings, usePageLocation } from "@/lib/settingsModal";
import { CofferLogo } from "./brand/CofferLogo";
import { DaemonOfflineBanner } from "./DaemonOfflineBanner";
import { FloatingBanners } from "./FloatingBanners";
import { SidebarNav } from "./SidebarNav";
import { SplitDivider } from "./SplitDivider";
import { CommandPalette } from "./palette/CommandPalette";
import { SidebarFooter } from "./shell/SidebarFooter";
import { SidebarLanguage } from "./shell/SidebarLanguage";
import { SidebarSearch } from "./shell/SidebarSearch";
import { useShellShortcuts } from "./shell/useShellShortcuts";

const COLLAPSE_KEY = "coffer.nav.collapsed";
// Tailwind's `md` breakpoint — the width at which the sidebar may expand.
const MD_QUERY = "(min-width: 768px)";
// The expanded sidebar's bounds and default (design board 1.1.21).
const SIDEBAR_MIN = 200;
const SIDEBAR_MAX = 300;
const SIDEBAR_DEFAULT = 220;

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeCollapsed(collapsed: boolean): void {
  try {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
  } catch {
    // Blocked storage: the choice holds for this visit.
  }
}

/** The Settings modal's routes, mounted only while one is open. */
function SettingsRoutes({ routes }: { routes: RouteObject[] }) {
  return useRoutes(routes);
}

interface Props {
  pageRoutes: RouteObject[];
  settingsRoutes: RouteObject[];
}

export function Layout({ pageRoutes, settingsRoutes }: Props) {
  const { t } = useTranslation();
  const location = useLocation();
  const pageLocation = usePageLocation();
  const page = useRoutes(pageRoutes, pageLocation);
  const settingsOpen = isSettingsPath(location.pathname);
  const openSettings = useOpenSettings();
  const [paletteOpen, setPaletteOpen] = useState(false);

  const [collapsedPref, setCollapsedPref] = useState(readCollapsed);
  // Where matchMedia is unavailable (jsdom) treat the viewport as md+.
  const isMd = useMediaQuery(MD_QUERY, true);
  const collapsed = collapsedPref || !isMd;
  const sidebar = useResizableWidth({
    storageKey: "sidebar",
    defaultWidth: SIDEBAR_DEFAULT,
    min: SIDEBAR_MIN,
    max: SIDEBAR_MAX,
  });

  const toggleCollapsed = () => {
    setCollapsedPref((prev) => {
      const next = !prev;
      writeCollapsed(next);
      return next;
    });
  };

  useShellShortcuts({
    togglePalette: () => setPaletteOpen((open) => !open),
    openSettings: () => {
      setPaletteOpen(false);
      openSettings("general");
    },
  });

  return (
    <TooltipProvider delayDuration={300}>
      {/* h-screen + overflow-hidden pins the app to the viewport; the sidebar
          and the main content each own an independent scroll region. */}
      <div className="flex h-screen overflow-hidden bg-background text-foreground">
        {/* First focusable element: lets keyboard users jump past the rail. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-ring"
        >
          {t("nav.skipToContent")}
        </a>
        {/* Floats over the whole app (fixed, top-centered) — rendered at the
            root so it overlays the sidebar too and never shifts page content.
            A vault that needs answering is a dot on the Sync entry instead
            (spec vault-sync "Say a vault needs a human where the user already
            is"). */}
        <FloatingBanners>
          <DaemonOfflineBanner />
        </FloatingBanners>
        <aside
          className={cn(
            "flex shrink-0 flex-col gap-3 bg-surface-sidebar",
            collapsed ? "w-14 border-r border-border" : null,
          )}
          // The dragged width is state, not a token: the one inline style is
          // this theming-free bridge from the divider to the rail.
          style={collapsed ? undefined : { width: sidebar.width }}
          data-testid="sidebar"
        >
          <div
            className={cn(
              "flex items-center pt-3.5",
              collapsed ? "flex-col justify-center gap-1 px-2" : "justify-between px-4",
            )}
          >
            <Link
              to="/"
              className="flex items-center rounded-item text-text"
              aria-label={collapsed ? "Coffer" : undefined}
            >
              <CofferLogo size={22} markOnly={collapsed} />
            </Link>
            {/* Expanding is only possible at md+; narrower viewports are
                always the icon rail, so the toggle is hidden there. */}
            {isMd ? (
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={toggleCollapsed}
                aria-label={t(collapsed ? "nav.expand" : "nav.collapse")}
                className={cn("shrink-0 text-muted-foreground", collapsed && "h-6 w-6")}
              >
                {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
              </Button>
            ) : null}
          </div>

          <SidebarSearch collapsed={collapsed} onOpen={() => setPaletteOpen(true)} />

          <SidebarNav collapsed={collapsed} pathname={pageLocation.pathname} />

          <div>
            <SidebarFooter collapsed={collapsed} />
            <SidebarLanguage collapsed={collapsed} />
          </div>
        </aside>
        {collapsed ? null : (
          <SplitDivider
            value={sidebar.width}
            min={sidebar.bounds.min}
            max={sidebar.bounds.max}
            onChange={sidebar.setWidth}
            onReset={sidebar.reset}
            label={t("nav.resizeSidebar")}
          />
        )}
        <main id="main" tabIndex={-1} className="flex-1 overflow-y-auto outline-none">
          {/* Full-width — the content tracks the sidebar, so collapsing it
              genuinely widens the working area. */}
          <div className="w-full px-6 py-10 md:px-10">{page}</div>
        </main>
      </div>
      {settingsOpen ? <SettingsRoutes routes={settingsRoutes} /> : null}
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </TooltipProvider>
  );
}
