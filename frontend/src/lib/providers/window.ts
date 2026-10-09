// src/lib/providers/window.ts — a context window as people write it: "128k", "1M".

/** 1000000 → "1M", 131072 → "131.1K": what a window is usually called, in
 *  every locale (Chinese model cards also say 128K, not 12.8万). */
export function formatWindow(tokens: number): string {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(
    tokens,
  );
}

const MIN = 1024;
const MAX = 100_000_000;

/** "128k" → 128000, "1m" → 1000000, "131072" → 131072; `null` when not a sane window. */
export function parseWindow(text: string): number | null {
  const m = /^\s*(\d+(?:\.\d+)?)\s*([km])?\s*$/i.exec(text.replace(/[,_]/g, ""));
  if (!m) return null;
  const scale = { k: 1_000, m: 1_000_000 }[(m[2] ?? "").toLowerCase()] ?? 1;
  const tokens = Math.round(Number(m[1]) * scale);
  return tokens >= MIN && tokens <= MAX ? tokens : null;
}
