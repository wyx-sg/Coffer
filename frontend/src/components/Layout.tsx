import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Boxes,
  PanelLeftClose,
  PanelLeftOpen,
  ScrollText,
  Server,
  Settings as SettingsIcon,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { DaemonOfflineBanner } from "./DaemonOfflineBanner";

const COLLAPSE_KEY = "coffer.nav.collapsed";

interface NavItem {
  to: string;
  labelKey: string;
  icon: LucideIcon;
  /** Match the path exactly (no prefix match) when deciding active state. */
  end?: boolean;
}

interface NavGroup {
  labelKey: string;
  items: NavItem[];
}

/**
 * Sidebar navigation. Coffer's UI ships only its operational surfaces — the
 * MCP gateway, observability, and settings. Planned resource kinds (skills,
 * knowledge bases, memory, channels, agents) and the Chat surface are not
 * shown until their feature lands.
 *
 * The two groups — **Resources** and **System** — exist from the start so
 * future kinds slot into Resources without re-doing the navigation. The
 * sidebar collapses to an icon-only rail; the choice persists in
 * localStorage. See spec 002-ui-shell §Information Architecture.
 */
const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: "nav.group.resources",
    items: [{ to: "/resources", labelKey: "nav.mcpServers", icon: Server, end: true }],
  },
  {
    labelKey: "nav.group.system",
    items: [
      { to: "/observability", labelKey: "nav.observability", icon: ScrollText },
      { to: "/settings", labelKey: "nav.settings", icon: SettingsIcon },
    ],
  },
];

function NavRow({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  const { t } = useTranslation();
  const label = t(item.labelKey);
  return (
    <NavLink
      to={item.to}
      end={item.end}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        cn(
          "flex items-center rounded-md py-2 font-medium transition-colors",
          collapsed ? "justify-center px-2" : "gap-2.5 px-3",
          isActive
            ? "bg-primary/10 text-primary"
            : "text-foreground/80 hover:bg-secondary hover:text-foreground",
        )
      }
    >
      <item.icon className="size-4 shrink-0" strokeWidth={1.75} />
      {!collapsed ? <span className="flex-1 truncate">{label}</span> : null}
    </NavLink>
  );
}

export function Layout() {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === "1");

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      return next;
    });
  };

  return (
    // h-screen + overflow-hidden pins the app to the viewport; the sidebar
    // and the main content each own an independent scroll region.
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <aside
        className={cn(
          "hidden shrink-0 flex-col border-r border-border bg-card/50 transition-[width] duration-200 md:flex",
          collapsed ? "w-16" : "w-64",
        )}
        aria-label={t("nav.aria.primary")}
      >
        <div
          className={cn(
            "flex h-16 items-center border-b border-border",
            collapsed ? "justify-center px-2" : "justify-between px-5",
          )}
        >
          {!collapsed ? (
            <Link to="/" className="flex items-center gap-2 text-base font-serif tracking-tight">
              <span
                className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground shadow-sm"
                aria-hidden
              >
                <Boxes className="size-4" strokeWidth={2.25} />
              </span>
              <span className="text-foreground">Coffer</span>
            </Link>
          ) : null}
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label={t(collapsed ? "nav.expand" : "nav.collapse")}
            title={t(collapsed ? "nav.expand" : "nav.collapse")}
            className="grid size-8 shrink-0 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            {collapsed ? (
              <PanelLeftOpen className="size-4" />
            ) : (
              <PanelLeftClose className="size-4" />
            )}
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-3 text-sm">
          {NAV_GROUPS.map((group, i) => (
            <div key={group.labelKey} className="mb-1">
              {collapsed ? (
                i > 0 ? (
                  <div className="mx-1 my-2 border-t border-border" />
                ) : null
              ) : (
                <div className="nav-group-label">{t(group.labelKey)}</div>
              )}
              {group.items.map((item) => (
                <NavRow key={item.to} item={item} collapsed={collapsed} />
              ))}
            </div>
          ))}
        </nav>

        {!collapsed ? (
          <div className="border-t border-border p-3">
            <LanguageSwitcher />
          </div>
        ) : null}
      </aside>
      <main className="flex-1 overflow-y-auto">
        {/* Full-width — the content tracks the sidebar, so collapsing it
            genuinely widens the working area. */}
        <div className="w-full px-6 py-10 md:px-10">
          <DaemonOfflineBanner />
          <Outlet />
        </div>
      </main>
    </div>
  );
}
