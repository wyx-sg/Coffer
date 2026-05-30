// frontend/src/lib/preferences.ts
//
// Small client-side UI preferences persisted in localStorage (same pattern as
// the sidebar-collapsed flag and the language choice). These are pure display
// settings — no user data — so they live in the browser, not the daemon.
import { useCallback, useSyncExternalStore } from "react";

const PAGE_SIZE_KEY = "coffer.pageSize";
export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 20;

export function getDefaultPageSize(): number {
  const raw = Number(localStorage.getItem(PAGE_SIZE_KEY));
  return PAGE_SIZE_OPTIONS.includes(raw as (typeof PAGE_SIZE_OPTIONS)[number])
    ? raw
    : DEFAULT_PAGE_SIZE;
}

// Tiny pub/sub so a change in Settings updates any mounted table live (the
// browser only fires the native `storage` event across tabs, not same-tab).
const listeners = new Set<() => void>();
function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function setDefaultPageSize(size: number): void {
  localStorage.setItem(PAGE_SIZE_KEY, String(size));
  listeners.forEach((cb) => cb());
}

/** Reactive read of the stored default page size. */
export function useDefaultPageSize(): number {
  return useSyncExternalStore(subscribe, getDefaultPageSize, () => DEFAULT_PAGE_SIZE);
}

/** Setter hook for the Settings control. */
export function useSetDefaultPageSize(): (size: number) => void {
  return useCallback((size: number) => setDefaultPageSize(size), []);
}
