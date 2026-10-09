// src/components/palette/paletteItems.ts — the command palette's entries as data, the query match that filters them, and the groups a query shows.
//
// Pure: no React, no i18n instance, no network. The component builds the
// entries (it owns the translated labels and the list hooks) and hands them
// here to be filtered, ranked and grouped, so the matching rule is tested on
// its own (spec web-ui "Jump to any page or object from a command palette").
//
// Every entry is a place to go. There is deliberately no "action" variant: the
// palette only navigates (change revise-web-ui-ia, design decision 6), so the
// only two targets are a route and a Settings tab.
import type { SettingsTabId } from "@/lib/navigation";

/** The object kinds the palette lists, in sidebar order — the order their
 *  groups appear in. */
export const OBJECT_KINDS = [
  "agent",
  "provider",
  "channel",
  "mcpServer",
  "customTool",
  "skill",
  "cli",
  "knowledge",
  "secret",
] as const;
export type ObjectKind = (typeof OBJECT_KINDS)[number];

/** What an entry is: a sidebar page, a Settings tab, or an object of a kind. */
export type PaletteKind = "page" | "settings" | ObjectKind;

/** Where an entry takes the user. */
export type PaletteTarget =
  | { type: "route"; to: string }
  | { type: "settings"; tab: SettingsTabId };

/** A status worth a word beside an object, as an i18n key under `palette.status`. */
export interface PaletteStatus {
  key:
    | "off"
    | "failing"
    | "attention"
    | "missing"
    | "notFound"
    | "outdated"
    | "loggedOut"
    | "running";
  tone: "muted" | "warn" | "error";
}

export interface PaletteItem {
  /** Unique across the palette, and a valid DOM id fragment once prefixed. */
  id: string;
  kind: PaletteKind;
  /** What the row shows. */
  label: string;
  /** Muted text after the label: an object's name when its title differs. */
  detail?: string;
  /** Extra muted meta on the right, already translated (a secret's users). */
  note?: string;
  status?: PaletteStatus;
  /** Every text the query is matched against. */
  haystack: string[];
  target: PaletteTarget;
}

/** Each kind's page — the sidebar entry its objects belong to (its group's
 *  name and icon) and the base of its detail route (spec web-ui "Lay out every
 *  detail page's tabs alike"). */
export const KIND_PAGE: Record<ObjectKind, string> = {
  agent: "/agents",
  provider: "/model-providers",
  channel: "/channels",
  mcpServer: "/mcp-servers",
  customTool: "/custom-tools",
  skill: "/skills",
  cli: "/clis",
  knowledge: "/knowledge",
  secret: "/secrets",
};

/** Every listed object carries a uid and a name; an agent
 *  also its type. `status` and `note` come from the list row when it carries
 *  them at no extra cost. */
export interface PaletteObject {
  uid: string;
  name: string;
  type?: string;
  status?: PaletteStatus;
  note?: string;
}

// A CLI is addressed by its command, which it carries as its name.
const ADDRESSED_BY_NAME: ReadonlySet<ObjectKind> = new Set([
  "mcpServer",
  "skill",
  "customTool",
  "cli",
]);

/** An object's detail route: by type for agents (one agent per type), by name
 *  where the kind's name is fixed, by uid where it can be
 *  renamed. A secret has no detail page, so it opens the Secrets page. */
export function objectPath(kind: ObjectKind, obj: PaletteObject): string {
  if (kind === "secret") return KIND_PAGE.secret;
  const id =
    kind === "agent" && obj.type ? obj.type : ADDRESSED_BY_NAME.has(kind) ? obj.name : obj.uid;
  return `${KIND_PAGE[kind]}/${encodeURIComponent(id)}`;
}

/** One object as a palette entry: shown and matched by its name. */
export function objectItem(kind: ObjectKind, obj: PaletteObject): PaletteItem {
  return {
    id: `${kind}-${obj.uid}`,
    kind,
    label: obj.name,
    note: obj.note,
    status: obj.status,
    haystack: [obj.name],
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

function isExact(item: PaletteItem, query: string): boolean {
  const q = query.trim().toLowerCase();
  return q !== "" && item.haystack.some((text) => text.toLowerCase() === q);
}

/** The entries that match `query`: an exact name first, then prefix matches,
 *  then the rest, otherwise in the order given (sidebar order for pages, list
 *  order for objects). */
export function filterItems(items: readonly PaletteItem[], query: string): PaletteItem[] {
  return items
    .map((item, index) => ({
      item,
      index,
      rank: matchRank(item, query),
      exact: isExact(item, query) ? 0 : 1,
    }))
    .filter((m) => m.rank !== null)
    .sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0) || a.exact - b.exact || a.index - b.index)
    .map((m) => m.item);
}

/** `text` split around the first case-insensitive occurrence of `query`, or
 *  `null` when it does not occur — what a row shows in bold. */
export function splitMatch(text: string, query: string): [string, string, string] | null {
  const q = query.trim();
  if (!q) return null;
  const at = text.toLowerCase().indexOf(q.toLowerCase());
  if (at < 0) return null;
  return [text.slice(0, at), text.slice(at, at + q.length), text.slice(at + q.length)];
}

/** At most this many entries per group under a query; typing more narrows. */
const GROUP_LIMIT = 4;

export interface PaletteGroup {
  /** "best", "pages", or the object kind the group holds. */
  key: "best" | "pages" | ObjectKind;
  items: PaletteItem[];
}

/**
 * The groups a non-empty query shows: "Best match" holding the single best
 * hit, then Pages, then one group per object kind in sidebar order, each
 * holding the rest of its hits up to `GROUP_LIMIT`. Empty when nothing matches.
 */
export function searchGroups(
  pages: readonly PaletteItem[],
  objects: readonly PaletteItem[],
  query: string,
): PaletteGroup[] {
  const hits = filterItems([...pages, ...objects], query);
  if (hits.length === 0) return [];
  const [best, ...rest] = hits;
  const groups: PaletteGroup[] = [{ key: "best", items: [best] }];
  const keys: PaletteGroup["key"][] = ["pages", ...OBJECT_KINDS];
  for (const key of keys) {
    const items = rest
      .filter((item) =>
        key === "pages" ? item.kind === "page" || item.kind === "settings" : item.kind === key,
      )
      .slice(0, GROUP_LIMIT);
    if (items.length > 0) groups.push({ key, items });
  }
  return groups;
}
