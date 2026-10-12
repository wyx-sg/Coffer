// frontend/src/lib/knowledge/treeState.ts
//
// What the person opened and closed in the Knowledge tree, kept in the browser
// so the tree comes back as they left it (spec knowledge "Show a collection as
// one tree of read-only documents in the web UI"): leaving the page, reloading
// it or opening it in another tab restores the same collections and folders.
// One record per kind — collections by uid, folders by their path under the
// knowledge root — each an `opened` and a `closed` list, because an item on
// the way to what is on screen is open unless the person closed it.
//
// Like the other per-viewer preferences (lib/preferences.ts) this is display
// state only: storage that is blocked or cleared falls back to everything
// closed, and nothing here reaches the daemon.
import { useCallback, useSyncExternalStore } from "react";

export type TreeKind = "collections" | "folders";

export interface TreeOpenState {
  opened: ReadonlySet<string>;
  closed: ReadonlySet<string>;
}

const keyOf = (kind: TreeKind) => `coffer.knowledge.tree.${kind}`;
const EMPTY: TreeOpenState = { opened: new Set(), closed: new Set() };

/** The stored text, or `undefined` where storage is blocked. */
function readRaw(kind: TreeKind): string | null | undefined {
  try {
    return localStorage.getItem(keyOf(kind));
  } catch {
    return undefined;
  }
}

// The snapshot must be the same object while the stored text is unchanged,
// or useSyncExternalStore re-renders forever. Where storage is blocked the
// state lives here instead, for the session.
const cache = new Map<TreeKind, { raw: string | null; state: TreeOpenState }>();

function parse(raw: string | null): TreeOpenState {
  if (!raw) return EMPTY;
  try {
    const value = JSON.parse(raw) as { opened?: unknown; closed?: unknown };
    const list = (v: unknown) =>
      Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
    return { opened: new Set(list(value.opened)), closed: new Set(list(value.closed)) };
  } catch {
    return EMPTY;
  }
}

function getTreeState(kind: TreeKind): TreeOpenState {
  const raw = readRaw(kind);
  const cached = cache.get(kind);
  if (raw === undefined) return cached?.state ?? EMPTY;
  if (cached && cached.raw === raw) return cached.state;
  const state = parse(raw);
  cache.set(kind, { raw, state });
  return state;
}

const listeners = new Set<() => void>();
function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  const onStorage = (e: StorageEvent) => {
    if (e.key?.startsWith("coffer.knowledge.tree.")) cb();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
}

/** Record that `id` was opened (true) or closed (false). */
function setTreeOpen(kind: TreeKind, id: string, open: boolean): void {
  const prev = getTreeState(kind);
  const opened = new Set(prev.opened);
  const closed = new Set(prev.closed);
  if (open) {
    opened.add(id);
    closed.delete(id);
  } else {
    opened.delete(id);
    closed.add(id);
  }
  const raw = JSON.stringify({ opened: [...opened], closed: [...closed] });
  cache.set(kind, { raw, state: { opened, closed } });
  try {
    localStorage.setItem(keyOf(kind), raw);
  } catch {
    // Not persisted; kept in the cache for this session.
  }
  listeners.forEach((cb) => cb());
}

/** Forget a closed mark, so the item opens again on the way to what is on screen. */
export function clearTreeClosed(kind: TreeKind, id: string): void {
  if (getTreeState(kind).closed.has(id)) setTreeOpen(kind, id, true);
}

/** The tree's open state for one kind, and a setter. */
export function useTreeState(kind: TreeKind) {
  const state = useSyncExternalStore(
    subscribe,
    () => getTreeState(kind),
    () => EMPTY,
  );
  const setOpen = useCallback((id: string, open: boolean) => setTreeOpen(kind, id, open), [kind]);
  return { ...state, setOpen };
}
