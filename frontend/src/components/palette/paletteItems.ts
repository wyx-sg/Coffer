// src/components/palette/paletteItems.ts — the command palette's entries as data, and the query match that filters them.
//
// Pure: no React, no i18n instance, no network. The component builds the
// entries (it owns the translated labels and the list hooks) and hands them
// here to be filtered and ranked, so the matching rule is tested on its own
// (spec web-ui "Jump to any page or object from a command palette").
//
// Every entry is a place to go. There is deliberately no "action" variant: the
// palette only navigates (change revise-web-ui-ia, design decision 6), so the
// only two targets are a route and a Settings tab.
import { displayName, titleOf, type Titled } from "@/lib/resourceTitle";
import type { SettingsTabId } from "@/lib/navigation";

/** The object kinds the palette lists. Custom tools are listed too by the
 *  spec; they join here when their page lands. */
export type ObjectKind =
  | "agent"
  | "mcpServer"
  | "skill"
  | "provider"
  | "channel"
  | "knowledge"
  | "memory"
  | "cli";

/** Where an entry takes the user. */
type PaletteTarget = { type: "route"; to: string } | { type: "settings"; tab: SettingsTabId };

export interface PaletteItem {
  /** Unique across the palette, and a valid DOM id fragment once prefixed. */
  id: string;
  group: "pages" | "objects";
  /** What the row shows. */
  label: string;
  /** Muted text after the label: an object's name when its title differs. */
  detail?: string;
  /** Muted kind word on the right of an object row. */
  kindLabel?: string;
  /** Every text the query is matched against. */
  haystack: string[];
  target: PaletteTarget;
}

/** The detail route of each kind's objects (spec web-ui "Lay out every detail
 *  page's tabs alike"): by type for agents (one agent per type), by name where
 *  the kind's name is fixed — MCP servers and skills — and by uid where it can
 *  be renamed. */
const DETAIL_BASE: Record<ObjectKind, string> = {
  agent: "/agents",
  mcpServer: "/mcp-servers",
  skill: "/skills",
  provider: "/model-providers",
  channel: "/channels",
  knowledge: "/knowledge",
  memory: "/memory",
  cli: "/clis",
};

/** Every listed object carries a uid, a name and an optional title; an agent also its type. */
export interface PaletteObject extends Titled {
  uid: string;
  type?: string;
}

// A CLI is addressed by its command, which it carries as its name.
const ADDRESSED_BY_NAME: ReadonlySet<ObjectKind> = new Set(["mcpServer", "skill", "cli"]);

export function objectPath(kind: ObjectKind, obj: PaletteObject): string {
  const id =
    kind === "agent" && obj.type ? obj.type : ADDRESSED_BY_NAME.has(kind) ? obj.name : obj.uid;
  return `${DETAIL_BASE[kind]}/${encodeURIComponent(id)}`;
}

/** One object as a palette entry: shown by its title when set (with its name
 *  after it), matched by both. */
export function objectItem(kind: ObjectKind, obj: PaletteObject, kindLabel: string): PaletteItem {
  const title = titleOf(obj);
  return {
    id: `${kind}-${obj.uid}`,
    group: "objects",
    label: displayName(obj),
    detail: title ? obj.name : undefined,
    kindLabel,
    haystack: title ? [title, obj.name] : [obj.name],
    target: { type: "route", to: objectPath(kind, obj) },
  };
}

/**
 * How well `item` matches `query`: 0 when some haystack text starts with it,
 * 1 when one contains it, `null` when none does. Case-insensitive; an empty
 * query matches everything at rank 0.
 */
export function matchRank(item: PaletteItem, query: string): 0 | 1 | null {
  const q = query.trim().toLowerCase();
  if (!q) return 0;
  let best: 0 | 1 | null = null;
  for (const text of item.haystack) {
    const hay = text.toLowerCase();
    if (hay.startsWith(q)) return 0;
    if (best === null && hay.includes(q)) best = 1;
  }
  return best;
}

/** The entries that match `query`, prefix matches first, otherwise in the
 *  order given (sidebar order for pages, list order for objects). */
export function filterItems(items: readonly PaletteItem[], query: string): PaletteItem[] {
  return items
    .map((item, index) => ({ item, index, rank: matchRank(item, query) }))
    .filter((m): m is { item: PaletteItem; index: number; rank: 0 | 1 } => m.rank !== null)
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map((m) => m.item);
}
