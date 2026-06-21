import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Bot,
  Boxes,
  Brain,
  MessageSquare,
  Library,
  PanelLeftClose,
  PanelLeftOpen,
  Radio,
  ScrollText,
  Server,
  Settings as SettingsIcon,
  Sparkles,
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
 * Sidebar navigation — a role-based information architecture (see ADR-007):
 *
 * - **Agents** — the consumers: the agents you use (Claude Code, Codex), Chat
 *   with them, and the Channels they communicate over. Agents are NOT vault
 *   assets, so they are not under Resources.
 * - **Resources** — the assets agents draw on, modelled as kind-agnostic
 *   resource kinds (MCP servers today; skills / knowledge / memory as they
 *   land), surfaced through the kind registry.
 * - **System** — cross-cutting tooling: the Audit log (who did what, when),
 *   Observability (system health/metrics — a distinct future surface), and
 *   Settings.
 *
 * Sidebar policy (ADR-007): show only what ships today — no "soon"
 * placeholders. Chat, Channels, the extra resource kinds, and Observability
 * appear as each feature lands. The sidebar collapses to an icon-only rail;
 * the choice persists in localStorage.
 */
const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: "nav.group.agents",
    items: [
      { to: "/chat", labelKey: "nav.chat", icon: MessageSquare },
      { to: "/agents", labelKey: "nav.agents", icon: Bot, end: true },
      { to: "/channels", labelKey: "nav.channels", icon: Radio, end: true },
    ],
  },
  {
    labelKey: "nav.group.resources",
    items: [
      { to: "/mcp-servers", labelKey: "nav.mcpServers", icon: Server, end: true },
      { to: "/skills", labelKey: "nav.skills", icon: Sparkles, end: true },
      { to: "/knowledge-bases", labelKey: "nav.knowledgeBases", icon: Library, end: true },
      { to: "/memory", labelKey: "nav.memory", icon: Brain, end: true },
    ],
  },
  {
    labelKey: "nav.group.system",
    items: [
      { to: "/audit", labelKey: "nav.audit", icon: ScrollText },
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
      {/* Floats over the whole app (fixed, top-centered) — rendered at the root
          so it overlays the sidebar too and never shifts page content. */}
      <DaemonOfflineBanner />
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
            <div key={group.labelKey || group.items[0]?.to} className="mb-1">
              {collapsed ? (
                i > 0 ? (
                  <div className="mx-1 my-2 border-t border-border" />
                ) : null
              ) : group.labelKey ? (
                <div className="nav-group-label">{t(group.labelKey)}</div>
              ) : null}
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
          <Outlet />
        </div>
      </main>
    </div>
  );
}
