// src/components/palette/paletteRecent.ts — the palette's Recent group: the last few choices, remembered per browser.
//
// A per-viewer convenience, so it lives in localStorage like the other display
// preferences (`lib/preferences.ts`), and every access is wrapped: in a private
// window or with site data blocked the palette simply has no Recent group.
// An entry keeps what is needed to show and open it before its kind's list
// has answered; once the list has answered the live row replaces it, or the
// entry is left out because the object no longer exists.
import type { KindState } from "./paletteSources";
import type { ObjectKind, PaletteItem, PaletteKind, PaletteTarget } from "./paletteItems";

const RECENT_KEY = "coffer.palette.recent";
/** How many choices the Recent group remembers. */
const RECENT_LIMIT = 5;

export interface RecentEntry {
  id: string;
  kind: PaletteKind;
  label: string;
  detail?: string;
  target: PaletteTarget;
  /** When it was chosen, ISO 8601. */
  at: string;
}

function isEntry(value: unknown): value is RecentEntry {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  const target = v.target as Record<string, unknown> | null | undefined;
  return (
    typeof v.id === "string" &&
    typeof v.kind === "string" &&
    typeof v.label === "string" &&
    typeof v.at === "string" &&
    typeof target === "object" &&
    target !== null &&
    (typeof target.to === "string" || typeof target.tab === "string")
  );
}

export function readRecent(): RecentEntry[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter(isEntry).slice(0, RECENT_LIMIT) : [];
  } catch {
    return [];
  }
}

/** Put `item` first in the Recent list, once, keeping the newest few. */
export function rememberChoice(item: PaletteItem, now: Date = new Date()): void {
  const entry: RecentEntry = {
    id: item.id,
    kind: item.kind,
    label: item.label,
    detail: item.detail,
    target: item.target,
    at: now.toISOString(),
  };
  const next = [entry, ...readRecent().filter((e) => e.id !== item.id)].slice(0, RECENT_LIMIT);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // Storage blocked or full: the choice is simply not remembered.
  }
}

export interface RecentItem {
  item: PaletteItem;
  at: string;
}

interface ResolveContext {
  /** The pages the palette lists now (a switched-off feature's are absent). */
  pages: readonly PaletteItem[];
  /** The kinds the palette may list now: none while the daemon is away. */
  liveKinds: readonly ObjectKind[];
  kinds: Partial<Record<ObjectKind, KindState>>;
  /** Every object entry of the kinds that have answered. */
  objects: readonly PaletteItem[];
}

/**
 * The Recent entries still worth showing, each as the live entry where there
 * is one: a page only while the palette lists it, an object only while its
 * kind may be listed, and — once its kind's list has answered — only while
 * the object is still in it.
 */
export function resolveRecent(entries: readonly RecentEntry[], ctx: ResolveContext): RecentItem[] {
  const out: RecentItem[] = [];
  for (const entry of entries) {
    if (entry.kind === "page" || entry.kind === "settings") {
      const page = ctx.pages.find((p) => p.id === entry.id);
      if (page) out.push({ item: page, at: entry.at });
      continue;
    }
    const kind = entry.kind;
    if (!ctx.liveKinds.includes(kind)) continue;
    if (ctx.kinds[kind]?.status === "success") {
      const live = ctx.objects.find((o) => o.id === entry.id);
      if (live) out.push({ item: live, at: entry.at });
      continue;
    }
    out.push({
      item: {
        id: entry.id,
        kind,
        label: entry.label,
        detail: entry.detail,
        haystack: [entry.label],
        target: entry.target,
      },
      at: entry.at,
    });
  }
  return out;
}
