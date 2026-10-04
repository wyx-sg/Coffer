// src/components/secret/secretListView.ts — the Secrets list as the page shows it: decorated rows, filtered, in the default order.
//
// Pure and computed once per change over the whole set (the page batches only what it
// renders), so search and filters answer instantly at a thousand secrets. The default order is
// layout principle 12: what needs you (no value on this Mac, a destination waiting) first, then by name.
import type { SecretRef } from "@/lib/api/secret";
import type { SecretListState, SecretStatus } from "@/lib/secrets/listState";
import { citersOf, hasPendingBinding, isMissingHere, shortName } from "./secretRows";

/** One row with what the list reads from it, worked out once. */
export interface SecretItem {
  row: SecretRef;
  short: string;
  /** A new destination waits for approval. */
  pending: boolean;
  /** This Mac has no value to hand out. */
  missing: boolean;
}

export function decorate(rows: readonly SecretRef[]): SecretItem[] {
  return rows.map((row) => ({
    row,
    short: shortName(row),
    pending: hasPendingBinding(row),
    missing: isMissingHere(row),
  }));
}

function matchesStatus(item: SecretItem, status: SecretStatus): boolean {
  switch (status) {
    case "all":
      return true;
    case "inUse":
      return !item.row.unreferenced;
    case "unused":
      return item.row.unreferenced;
  }
}

/** Search matches the secret's name and the names of what uses it. */
function matchesSearch(item: SecretItem, q: string): boolean {
  if (!q) return true;
  return (
    item.row.ref.toLowerCase().includes(q) ||
    item.short.toLowerCase().includes(q) ||
    citersOf(item.row).some((c) => c.name.toLowerCase().includes(q))
  );
}

/** The items the search text and the status keep. */
export function filterItems(items: SecretItem[], state: SecretListState): SecretItem[] {
  const q = state.q.trim().toLowerCase();
  return items.filter((i) => matchesSearch(i, q) && matchesStatus(i, state.status));
}

const text = (a: string, b: string) => a.localeCompare(b, undefined, { sensitivity: "base" });

/** Default order: no value / waiting first, then by name. */
export function defaultOrder(items: SecretItem[]): SecretItem[] {
  const needs = (i: SecretItem) => Number(i.missing || i.pending);
  return [...items].sort(
    (a, b) => needs(b) - needs(a) || text(a.short, b.short) || text(a.row.ref, b.row.ref),
  );
}

/** What a secret's delete is up against: only a stored secret nothing uses and nothing waits on can go. */
export function isDeletable(item: SecretItem): boolean {
  return item.row.unreferenced && item.row.present && !item.pending;
}
