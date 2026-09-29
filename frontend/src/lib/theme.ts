// frontend/src/lib/theme.ts
//
// Light / dark theme. The viewer picks "system" (the default: follow the OS
// appearance, live), "light" or "dark"; the choice is a per-viewer display
// preference, so it lives in this browser's localStorage under `coffer.theme`
// and never reaches the daemon. What the page renders is the RESOLVED theme,
// written to <html data-theme="light|dark">; src/index.css re-points every
// colour token under `[data-theme="dark"]`, so no component knows which theme
// is on screen.
import { useCallback, useSyncExternalStore } from "react";

export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_PREFERENCES: readonly ThemePreference[] = ["system", "light", "dark"];
const THEME_KEY = "coffer.theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

function isPreference(value: unknown): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

/** The stored preference; "system" when nothing (or nothing valid) is stored,
 *  or when storage is unavailable (private window, blocked site data). */
export function getThemePreference(): ThemePreference {
  try {
    const raw = localStorage.getItem(THEME_KEY);
    return isPreference(raw) ? raw : "system";
  } catch {
    return "system";
  }
}

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches;
}

/** The theme a preference renders as, given whether the OS is in dark mode. */
export function resolveTheme(preference: ThemePreference, systemDark: boolean): ResolvedTheme {
  if (preference === "system") return systemDark ? "dark" : "light";
  return preference;
}

// Only used when localStorage throws, so a choice still sticks until reload.
let overrideForSession: ThemePreference | null = null;

function currentPreference(): ThemePreference {
  return overrideForSession ?? getThemePreference();
}

const listeners = new Set<() => void>();
function notify(): void {
  listeners.forEach((cb) => cb());
}
function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Write the resolved theme onto <html>. */
export function applyTheme(root: HTMLElement = document.documentElement): ResolvedTheme {
  const theme = resolveTheme(currentPreference(), systemPrefersDark());
  root.dataset.theme = theme;
  return theme;
}

export function setThemePreference(preference: ThemePreference): void {
  overrideForSession = null;
  try {
    if (preference === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, preference);
  } catch {
    // Storage unavailable: the choice still applies for this page view.
    overrideForSession = preference;
  }
  applyTheme();
  notify();
}

/**
 * Apply the theme now and keep it in step with the OS appearance (while the
 * preference is "system") and with other tabs changing the preference. Call
 * once, before the first render. Returns a teardown for tests.
 */
export function initTheme(): () => void {
  applyTheme();
  const onChange = () => {
    applyTheme();
    notify();
  };
  const media = typeof window.matchMedia === "function" ? window.matchMedia(DARK_QUERY) : null;
  media?.addEventListener?.("change", onChange);
  const onStorage = (event: StorageEvent) => {
    if (event.key === THEME_KEY) onChange();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    media?.removeEventListener?.("change", onChange);
    window.removeEventListener("storage", onStorage);
  };
}

/** Reactive read of the viewer's theme preference (for the picker). */
export function useThemePreference(): ThemePreference {
  return useSyncExternalStore(subscribe, currentPreference, () => "system");
}

/** Setter hook for the theme picker. */
export function useSetThemePreference(): (preference: ThemePreference) => void {
  return useCallback((preference: ThemePreference) => setThemePreference(preference), []);
}
