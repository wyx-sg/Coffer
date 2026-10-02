// frontend/src/lib/preferences.ts
//
// Small client-side UI preferences persisted in localStorage (same pattern as
// the sidebar-collapsed flag and the language choice). These are pure display
// settings — no user data — so they live in the browser, not the daemon.
import { useCallback, useSyncExternalStore } from "react";

// Storage can be blocked (private windows, cleared or denied site data): every
// read falls back to the default and every write is skipped, because these are
// per-viewer conveniences and `getSnapshot` runs in render.
function readStored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Not persisted; the choice lasts until the page reloads.
  }
}

const PAGE_SIZE_KEY = "coffer.pageSize";
export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 20;

export function getDefaultPageSize(): number {
  const raw = Number(readStored(PAGE_SIZE_KEY));
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
  writeStored(PAGE_SIZE_KEY, String(size));
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

const PREFERRED_EDITOR_KEY = "coffer.preferredEditor";

/**
 * The user's preferred external editor for opening managed files. The stored
 * value is an application name / path or a launch command (e.g. "code",
 * "cursor", or a full ".app" path). An empty string means "use the operating
 * system's default application". Like the page-size preference this lives in
 * the browser, never the daemon.
 */
export function getPreferredEditor(): string {
  return readStored(PREFERRED_EDITOR_KEY) ?? "";
}

function setPreferredEditor(editor: string): void {
  const trimmed = editor.trim();
  if (trimmed) {
    writeStored(PREFERRED_EDITOR_KEY, trimmed);
  } else {
    // Empty / whitespace clears the override → fall back to the OS default.
    writeStored(PREFERRED_EDITOR_KEY, null);
  }
  listeners.forEach((cb) => cb());
}

/** Reactive read of the preferred external editor ("" = OS default). */
export function usePreferredEditor(): string {
  return useSyncExternalStore(subscribe, getPreferredEditor, () => "");
}

/** Setter hook for the Settings control. */
export function useSetPreferredEditor(): (editor: string) => void {
  return useCallback((editor: string) => setPreferredEditor(editor), []);
}
