// src/lib/providers/priceSource.ts — where most of a provider's model prices come from.
import type { ModelPrice } from "@/lib/api/providers";

/** The one line under Models' title: where this provider's prices come from, unless a row says otherwise. */
export function providerPriceSource(prices: readonly ModelPrice[]): {
  source: NonNullable<ModelPrice["source"]>;
  name: string | null;
  updated: string | null;
} | null {
  const counts = new Map<string, { n: number; price: ModelPrice }>();
  for (const p of prices) {
    if (!p.source || p.source === "user" || p.source === "local") continue;
    const hit = counts.get(p.source);
    if (hit) hit.n += 1;
    else counts.set(p.source, { n: 1, price: p });
  }
  const best = [...counts.values()].sort((a, b) => b.n - a.n)[0];
  if (!best) return null;
  return {
    source: best.price.source as NonNullable<ModelPrice["source"]>,
    name: best.price.source_name,
    updated: best.price.source_updated,
  };
}
