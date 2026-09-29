// src/components/brand/cofferMarkStroke.ts — the mark's stroke width, raised at small sizes so it never renders under 1.5px.

/** Stroke width on the 24 grid: 1.75, raised so it never renders under 1.5px. */
export function cofferMarkStroke(size: number): number {
  return Math.max(1.75, (1.5 * 24) / size);
}
