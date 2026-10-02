// src/lib/navigation.ts — the app's information architecture as data: the sidebar's entries and the Settings tabs.
//
// One list read by three surfaces — the sidebar, the command palette's Pages
// group and the Settings modal's tab strip — so a surface carries one name and
// one route everywhere (spec web-ui "Call a surface by one name everywhere").
//
// The sidebar is grouped by what the person comes to do (ADR
// sidebar-grouped-by-what-the-person-comes-to-do): Overview under no heading,
// then Agents · Run · Capabilities · Context · System — fifteen entries, and no
// sixteenth without a spec change (spec web-ui "Keep the sidebar to its
// fifteen entries"). Settings is not an entry: it is a modal opened from the
// labelled row in the sidebar footer, from ⌘, and from the palette.
import {
  Activity as DaemonIcon,
  Bot,
  Boxes,
  Brain,
  Database,
  FlaskConical,
  Gauge,
  Info,
  KeyRound,
  LayoutDashboard,
  Library,
  MessageSquare,
  Radio,
  RefreshCw,
  ScrollText,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  SquareTerminal,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import type { FeatureKey } from "@/lib/features";

export interface NavEntry {
  to: string;
  labelKey: string;
  icon: LucideIcon;
  /** The experimental feature the entry belongs to; while it is not switched
   *  on the entry is left out of the sidebar and the palette, and its page is
   *  not found (spec experimental-features "Close every surface of a
   *  switched-off feature"). */
  feature?: FeatureKey;
}

export interface NavGroup {
  /** `null` for the ungrouped Overview entry that sits above the headings. */
  labelKey: string | null;
  entries: NavEntry[];
}

export const NAV_GROUPS: readonly NavGroup[] = [
  {
    // Overview summarises all five groups, so it is filed under none of them.
    labelKey: null,
    entries: [{ to: "/", labelKey: "nav.overview", icon: LayoutDashboard }],
  },
  {
    // Set up the agents and the models they run on.
    labelKey: "nav.group.agents",
    entries: [
      { to: "/agents", labelKey: "nav.agents", icon: Bot },
      { to: "/model-providers", labelKey: "nav.modelProviders", icon: Boxes, feature: "models" },
    ],
  },
  {
    // Put an agent to work, directly or through an IM bot.
    labelKey: "nav.group.run",
    entries: [
      { to: "/conversations", labelKey: "nav.conversations", icon: MessageSquare },
      { to: "/channels", labelKey: "nav.channels", icon: Radio },
    ],
  },
  {
    // Give agents things they can do.
    labelKey: "nav.group.capabilities",
    entries: [
      { to: "/mcp-servers", labelKey: "nav.mcpServers", icon: Server },
      { to: "/custom-tools", labelKey: "nav.customTools", icon: Wrench },
      { to: "/skills", labelKey: "nav.skills", icon: Sparkles },
      { to: "/clis", labelKey: "nav.clis", icon: SquareTerminal },
    ],
  },
  {
    // Give agents things they know.
    labelKey: "nav.group.context",
    entries: [
      { to: "/knowledge", labelKey: "nav.knowledge", icon: Library, feature: "knowledge" },
      { to: "/memory", labelKey: "nav.memory", icon: Brain, feature: "memory" },
    ],
  },
  {
    // Look after Coffer and what every other part shares.
    labelKey: "nav.group.system",
    entries: [
      { to: "/secrets", labelKey: "nav.secrets", icon: KeyRound },
      { to: "/activity", labelKey: "nav.activity", icon: ScrollText },
      { to: "/usage", labelKey: "nav.usage", icon: Gauge, feature: "models" },
      { to: "/sync", labelKey: "nav.sync", icon: RefreshCw, feature: "sync" },
    ],
  },
];

/** Every sidebar entry, in sidebar order. */
export const NAV_ENTRIES: readonly NavEntry[] = NAV_GROUPS.flatMap((g) => g.entries);

export type SettingsTabId = "general" | "security" | "data" | "daemon" | "features" | "about";

export interface SettingsTab {
  id: SettingsTabId;
  labelKey: string;
  icon: LucideIcon;
}

/** The Settings modal's six tabs, in order (spec web-ui "Organise Settings
 *  into six tabs"), the same in every build. Each is addressable at
 *  `/settings/<id>`; Features is where the experimental features are switched
 *  (spec experimental-features "Switch a feature from the settings page or the
 *  command line"), and About, last, says what is installed. */
export const SETTINGS_TABS: readonly SettingsTab[] = [
  { id: "general", labelKey: "settings.tabs.general", icon: SlidersHorizontal },
  { id: "security", labelKey: "settings.tabs.security", icon: ShieldCheck },
  { id: "data", labelKey: "settings.tabs.data", icon: Database },
  { id: "daemon", labelKey: "settings.tabs.daemon", icon: DaemonIcon },
  { id: "features", labelKey: "settings.tabs.features", icon: FlaskConical },
  { id: "about", labelKey: "settings.tabs.about", icon: Info },
];

export function settingsPath(tab: SettingsTabId = "general"): string {
  return `/settings/${tab}`;
}

/** Whether a pathname is one of the Settings modal's routes. */
export function isSettingsPath(pathname: string): boolean {
  return pathname === "/settings" || pathname.startsWith("/settings/");
}

/** Edit distance between two short strings. */
function distance(a: string, b: string): number {
  const row = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i += 1) {
    let prev = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j += 1) {
      const next = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = next;
    }
  }
  return row[b.length];
}

/** The sidebar page nearest an unknown address (the 404's "Did you mean"):
 *  the page nearest the address's first segment, or null when none is close. */
export function closestPage(pathname: string): string | null {
  const head = pathname.split("/").filter(Boolean)[0]?.toLowerCase();
  if (!head) return null;
  let best: { to: string; score: number } | null = null;
  for (const { to } of NAV_ENTRIES) {
    const name = to.slice(1);
    if (!name) continue;
    // A prefix of a page's address ("mcp" of "mcp-servers") is as close as it gets.
    const score = name.startsWith(head) ? 0 : distance(head, name);
    if (best === null || score < best.score) best = { to, score };
  }
  return best && best.score <= Math.max(2, Math.floor(head.length / 3)) ? best.to : null;
}
