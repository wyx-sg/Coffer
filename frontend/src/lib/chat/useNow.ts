// src/lib/chat/useNow.ts — the current time in ms, ticking each second while
// `active`; a still-running reply's "Working · 1m 12s" runs on it.
import { useEffect, useState } from "react";

export function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}
