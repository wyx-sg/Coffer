// src/lib/hooks/useMediaQuery.ts — subscribe to a CSS media query from React.
// Falls back to `fallback` where matchMedia is unavailable (jsdom, SSR), so
// callers never branch on `window` themselves.
import { useSyncExternalStore } from "react";

function subscribe(query: string, onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return () => {};
  }
  const mql = window.matchMedia(query);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}

export function useMediaQuery(query: string, fallback = false): boolean {
  return useSyncExternalStore(
    (onChange) => subscribe(query, onChange),
    () =>
      typeof window !== "undefined" && typeof window.matchMedia === "function"
        ? window.matchMedia(query).matches
        : fallback,
    () => fallback,
  );
}
