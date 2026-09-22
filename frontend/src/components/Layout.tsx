// src/components/Layout.tsx — the app shell: sidebar rail + scrolling main region.
//
// The rail is always present. At md+ it can expand to a labelled 64-wide
// sidebar (the choice persists in localStorage); below md it is always the
// 16-wide icon rail, so narrow viewports keep their navigation. Collapsed rows
// get a tooltip and the language switcher folds into a globe popover.
import { useState } from "react";
import { Link, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Boxes, Globe, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useMediaQuery } from "@/lib/hooks/useMediaQuery";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { DaemonOfflineBanner } from "./DaemonOfflineBanner";
import { FloatingBanners } from "./FloatingBanners";
import { SyncAttentionBanner } from "./SyncAttentionBanner";
import { SidebarNav } from "./SidebarNav";

const COLLAPSE_KEY = "coffer.nav.collapsed";
// Tailwind's `md` breakpoint — the width at which the sidebar may expand.
const MD_QUERY = "(min-width: 768px)";

export function Layout() {
  const { t } = useTranslation();
  const [collapsedPref, setCollapsedPref] = useState(
    () => localStorage.getItem(COLLAPSE_KEY) === "1",
  );
  // Where matchMedia is unavailable (jsdom) treat the viewport as md+.
  const isMd = useMediaQuery(MD_QUERY, true);
  const collapsed = collapsedPref || !isMd;

  const toggleCollapsed = () => {
    setCollapsedPref((prev) => {
      const next = !prev;
      localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      return next;
    });
  };

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
            Both banners can be up at once: an out-of-date daemon answers the
            sync status perfectly well, and a held round is still cached while
            a newly-failed status query retries. They stack, because each is a
            different thing to do something about. */}
        <FloatingBanners>
          <DaemonOfflineBanner />
          {/* A held or failed round has to reach the user wherever they are:
              the Sync page is the one place they have no reason to open, and a
              vault waiting on an answer converges no further until it gets one
              (spec vault-sync FR-096). */}
          <SyncAttentionBanner />
        </FloatingBanners>
        <aside
          className={cn(
            "flex shrink-0 flex-col border-r border-border bg-card/50 transition-[width] duration-200",
            collapsed ? "w-16" : "w-64",
          )}
          aria-label={t("nav.aria.primary")}
        >
          <div
            className={cn(
              "flex h-16 items-center border-b border-border",
              collapsed ? "flex-col justify-center gap-1 px-2" : "justify-between px-5",
            )}
          >
            <Link
              to="/"
              className="flex items-center gap-2 text-base font-serif tracking-tight"
              aria-label={collapsed ? "Coffer" : undefined}
            >
              <span
                className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground shadow-sm"
                aria-hidden
              >
                <Boxes className="size-4" strokeWidth={2.25} />
              </span>
              {!collapsed ? <span className="text-foreground">Coffer</span> : null}
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

          <SidebarNav collapsed={collapsed} />

          <div
            className={cn("border-t border-border", collapsed ? "flex justify-center p-2" : "p-3")}
          >
            {collapsed ? (
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("nav.language")}
                    className="text-muted-foreground"
                  >
                    <Globe />
                  </Button>
                </PopoverTrigger>
                <PopoverContent side="right" align="end" className="w-auto p-3">
                  <LanguageSwitcher />
                </PopoverContent>
              </Popover>
            ) : (
              <LanguageSwitcher />
            )}
          </div>
        </aside>
        <main id="main" tabIndex={-1} className="flex-1 overflow-y-auto outline-none">
          {/* Full-width — the content tracks the sidebar, so collapsing it
              genuinely widens the working area. */}
          <div className="w-full px-6 py-10 md:px-10">
            <Outlet />
          </div>
        </main>
      </div>
    </TooltipProvider>
  );
}
