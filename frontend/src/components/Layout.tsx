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
// keep their navigation. Collapsed rows get a tooltip, and the expand control
// stays at the top of the rail, under the brand mark. Theme and language live
// in Settings › General.
//
// The desktop shell draws its own title strip across the top (board 1.1.02):
// the sidebar toggle and the back / forward arrows live there, and the
// sidebar and the page both start under it. The sidebar's content starts 12px
// below the strip; the page keeps 16px above its content and 32px at each side.
//
// The daemon's connection states are drawn in the workspace, in line
// (boards 1.1.18 / 1.1.19): the bar sits right under the title strip; while
// reconnecting the page stays under it,
// dimmed and inert; once offline it makes way for the offline screen; when the
// daemon answers again every query refetches and a toast says so.
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useRoutes, type RouteObject } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useMediaQuery } from "@/lib/hooks/useMediaQuery";
import { useHistoryNav } from "@/lib/hooks/useHistoryNav";
import { useResizableWidth } from "@/lib/hooks/useResizableWidth";
import { isSettingsPath } from "@/lib/navigation";
import { overlayTitleBar } from "@/lib/windowChrome";
import { SidebarBrandRow } from "./shell/SidebarBrandRow";
import { TitleBarSlotContext } from "./shell/titleBarSlot";
import { WindowTitleStrip } from "./shell/WindowTitleStrip";
import { useOpenSettings, usePageLocation } from "@/lib/settingsModal";
import { DaemonOfflineState, DaemonStatusBar } from "./DaemonOfflineBanner";
import { SidebarNav } from "./SidebarNav";
import { PendingApprovalsSheet } from "./secret/PendingApprovalsSheet";
import { SplitDivider } from "./SplitDivider";
import { CommandPalette } from "./palette/CommandPalette";
import { useDaemonConnectionDriver } from "./shell/daemonConnection";
import { SidebarFooter } from "./shell/SidebarFooter";
import { SidebarSearch } from "./shell/SidebarSearch";
import { usePaletteRequests } from "./shell/paletteRequest";
import { useShellShortcuts } from "./shell/useShellShortcuts";

const COLLAPSE_KEY = "coffer.nav.collapsed";
// Tailwind's `md` breakpoint — the width at which the sidebar may expand.
const MD_QUERY = "(min-width: 768px)";
// The expanded sidebar's bounds and default (the sidebar component board).
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
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const overlay = overlayTitleBar();
  const [titleSlot, setTitleSlot] = useState<HTMLElement | null>(null);
  const { toast } = useToast();
  const daemon = useDaemonConnectionDriver(() => toast.success(t("daemon.reconnect.reconnected")));
  const phase = daemon.connection.phase;
  // A dimmed page must not take keystrokes either; `inert` is not a React prop yet.
  const pageRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    pageRef.current?.toggleAttribute("inert", phase === "reconnecting");
  }, [phase]);

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

  const history = useHistoryNav();

  usePaletteRequests(openPalette);
  useShellShortcuts({
    toggleSidebar: isMd ? toggleCollapsed : undefined,
    goBack: overlay ? history.goBack : undefined,
    goForward: overlay ? history.goForward : undefined,
    togglePalette: () => setPaletteOpen((open) => !open),
    openSettings: () => {
      setPaletteOpen(false);
      openSettings("general");
    },
  });

  return (
    <TooltipProvider>
      {/* h-[100vh] + overflow-hidden pins the app to the viewport; the sidebar
          and the main content each own an independent scroll region. */}
      <div className="flex h-[100vh] overflow-hidden bg-background text-foreground">
        {/* First focusable element: lets keyboard users jump past the rail. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-toast focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:shadow-overlay focus:outline-none focus:ring-2 focus:ring-ring"
        >
          {t("nav.skipToContent")}
        </a>
        {overlay ? (
          <WindowTitleStrip
            showToggle={isMd}
            collapsed={collapsed}
            onToggle={toggleCollapsed}
            sidebarWidth={sidebar.width}
            onBack={history.goBack}
            onForward={history.goForward}
            onSlot={setTitleSlot}
          />
        ) : null}
        {/* Once for the whole app: a secret change waiting for a present
            human is answered wherever the user is, not on one page. */}
        <PendingApprovalsSheet />
        <aside
          className={cn(
            "flex shrink-0 flex-col gap-3.5 bg-surface-sidebar",
            collapsed ? "w-rail border-r border-border" : null,
            // The desktop shell's sidebar starts 12px under the title strip, with
            // no brand row; the strip holds the traffic lights, the toggle and the arrows.
            overlay ? "pt-[calc(var(--titlebar-inset)+12px)]" : null,
          )}
          // The dragged width is state, not a token: the one inline style is
          // this theming-free bridge from the divider to the rail.
          style={collapsed ? undefined : { width: sidebar.width }}
          id="sidebar"
          data-testid="sidebar"
        >
          {overlay ? null : (
            <SidebarBrandRow collapsed={collapsed} showToggle={isMd} onToggle={toggleCollapsed} />
          )}

          <SidebarSearch collapsed={collapsed} onOpen={openPalette} />

          <SidebarNav collapsed={collapsed} pathname={pageLocation.pathname} />

          <SidebarFooter collapsed={collapsed} />
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
        {/* The main column starts under the title strip, so neither the
            connection bar nor a page header ever sits beneath it; full-bleed
            pages (`h-screen`) shrink by the same inset through index.css. */}
        <main
          id="main"
          tabIndex={-1}
          className="flex min-w-0 flex-1 flex-col pt-[var(--titlebar-inset)] outline-none"
        >
          <DaemonStatusBar connection={daemon.connection} onRetry={daemon.retryNow} />
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto" data-testid="page-scroll">
            {phase === "offline" ? (
              <DaemonOfflineState connection={daemon.connection} onRetry={daemon.retryNow} />
            ) : (
              // Full-width — the content tracks the sidebar, so collapsing it
              // genuinely widens the working area.
              <div
                ref={pageRef}
                aria-busy={phase === "reconnecting" || undefined}
                className={cn(
                  "w-full px-8 pb-10 pt-4",
                  phase === "reconnecting" && "pointer-events-none select-none opacity-[.55]",
                )}
              >
                <TitleBarSlotContext.Provider value={titleSlot}>
                  {page}
                </TitleBarSlotContext.Provider>
              </div>
            )}
          </div>
        </main>
      </div>
      {settingsOpen ? <SettingsRoutes routes={settingsRoutes} /> : null}
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </TooltipProvider>
  );
}
