// src/components/SidebarNav.tsx — the sidebar's navigation groups and rows.
// Layout owns the rail (width, collapse state, brand, footer); this file owns
// what goes in it: the information architecture and one row's rendering.
import { useTranslation } from "react-i18next";
import { Link, useMatch } from "react-router-dom";
import {
  Bot,
  Boxes,
  Brain,
  MessageSquare,
  Library,
  Radio,
  RefreshCw,
  Server,
  ScrollText,
  Settings as SettingsIcon,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useSyncAttention } from "@/lib/hooks/useSyncAttention";
import { useFeatureEnabled, type FeatureKey } from "@/lib/hooks/useFeatures";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  labelKey: string;
  icon: LucideIcon;
  /** The experimental feature the entry belongs to; while it is not switched
   *  on the entry is left out (spec experimental-features "Close every surface
   *  of a switched-off feature"). */
  feature?: FeatureKey;
}

interface NavGroup {
  labelKey: string;
  items: NavItem[];
}

/**
 * Sidebar navigation — a role-based information architecture (ADR everything-is-a-resource-kind):
 *
 * - **Agents** — the consumers: the agents you use (Claude Code, Codex), and
 *   Chat with them. Agents are NOT vault assets, so they are not under
 *   Resources.
 * - **Resources** — the assets agents draw on, one entry per resource kind
 *   that has a list UI: MCP servers, skills, knowledge, memory, model
 *   providers and channels. A channel is a credentialed transport the vault
 *   owns, so it belongs here rather than beside the agents that happen to
 *   answer on it.
 * - **System** — cross-cutting tooling: Activity (the three records Coffer
 *   keeps, a tab and a table each) and Settings. Observability (system health
 *   / metrics) is a reserved future surface and is not Activity: a record of
 *   what happened is not a measurement of how the system is doing.
 *
 * Sidebar policy (ADR everything-is-a-resource-kind): show only what ships today — no "soon"
 * placeholders, and no entry outliving its feature.
 *
 * Every entry matches by path prefix (segment-aware), so a detail page keeps
 * its list's entry highlighted: /agents/codex lights up Agents.
 */
const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: "nav.group.agents",
    items: [
      // Agents first: the agents are the subject, and a chat is one thing you
      // do with one of them.
      { to: "/agents", labelKey: "nav.agents", icon: Bot },
      { to: "/chat", labelKey: "nav.chat", icon: MessageSquare },
    ],
  },
  {
    // One entry per resource kind with a list UI — mcp_server, skill,
    // knowledge, memory, provider, channel. Keeping that one-to-one is the
    // whole rule; Model providers and Channels were the two that had drifted
    // out of it.
    labelKey: "nav.group.resources",
    items: [
      { to: "/mcp-servers", labelKey: "nav.mcpServers", icon: Server },
      { to: "/skills", labelKey: "nav.skills", icon: Sparkles },
      { to: "/knowledge", labelKey: "nav.knowledge", icon: Library, feature: "knowledge" },
      { to: "/memory", labelKey: "nav.memory", icon: Brain, feature: "memory" },
      { to: "/model-providers", labelKey: "nav.modelProviders", icon: Boxes },
      { to: "/channels", labelKey: "nav.channels", icon: Radio },
    ],
  },
  {
    labelKey: "nav.group.system",
    items: [
      { to: "/activity", labelKey: "nav.activity", icon: ScrollText },
      { to: "/sync", labelKey: "nav.sync", icon: RefreshCw, feature: "vault_sync" },
      { to: "/settings", labelKey: "nav.settings", icon: SettingsIcon },
    ],
  },
];

function NavRow({ item, collapsed, dot }: { item: NavItem; collapsed: boolean; dot: boolean }) {
  const { t } = useTranslation();
  const label = t(item.labelKey);
  // A plain Link + useMatch rather than NavLink: NavLink's className callback
  // cannot pass through TooltipTrigger's Slot (it stringifies functions).
  const isActive = useMatch({ path: item.to, end: false }) !== null;
  const link = (
    <Link
      to={item.to}
      aria-current={isActive ? "page" : undefined}
      aria-label={collapsed ? label : undefined}
      className={cn(
        "relative flex items-center rounded-md py-2 font-medium transition-colors",
        collapsed ? "justify-center px-2" : "gap-2.5 px-3",
        isActive
          ? "bg-primary/10 text-primary"
          : "text-foreground/80 hover:bg-secondary hover:text-foreground",
      )}
    >
      <item.icon className="size-4 shrink-0" strokeWidth={1.75} />
      {!collapsed ? <span className="flex-1 truncate">{label}</span> : null}
      {/* A dot, not a count: what is waiting is one situation to look at, and
          a number here would be the number of times the timer re-raised it.
          On a collapsed rail it rides the icon, which is all there is. */}
      {dot ? (
        <span
          data-testid={`nav-dot-${item.to.replace(/\//g, "")}`}
          aria-label={t("nav.needsAttention")}
          className={cn(
            "size-1.5 shrink-0 rounded-full bg-destructive",
            collapsed ? "absolute right-1.5 top-1.5" : null,
          )}
        />
      ) : null}
    </Link>
  );
  if (!collapsed) return link;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}

export function SidebarNav({ collapsed }: { collapsed: boolean }) {
  const { t } = useTranslation();
  // A held or failed vault stops converging and stops backing up, and the one
  // surface that says so is the page a user has no reason to open. The dot is
  // what gets them there; going there is what clears it.
  const syncNeedsAttention = useSyncAttention();
  // An entry whose feature is off — or not known yet — is left out rather
  // than flashed in and taken away again: on a stable build the three are off.
  const on: Record<FeatureKey, boolean> = {
    vault_sync: useFeatureEnabled("vault_sync") === true,
    knowledge: useFeatureEnabled("knowledge") === true,
    memory: useFeatureEnabled("memory") === true,
  };
  const shown = (item: NavItem) => item.feature === undefined || on[item.feature];
  return (
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
          {group.items.filter(shown).map((item) => (
            <NavRow
              key={item.to}
              item={item}
              collapsed={collapsed}
              dot={item.to === "/sync" && syncNeedsAttention}
            />
          ))}
        </div>
      ))}
    </nav>
  );
}
