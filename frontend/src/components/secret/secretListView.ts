// src/components/secret/secretListView.ts — the Secrets list as the page shows it: decorated rows, filtered, sorted, counted, grouped.
//
// Pure and computed once per change over the whole set (the page batches only what it
// renders), so search and filters answer instantly at a thousand secrets.
import type { SecretRef } from "@/lib/api/secret";
import type { SecretListState, SecretStatus } from "@/lib/secrets/listState";
import { hasPendingBinding } from "./secretRows";
import { ownerOf, shortName, type Owner } from "./secretOwners";

/** One row with what the list reads from it, worked out once. */
export interface SecretItem {
  row: SecretRef;
  short: string;
  owner: Owner;
  /** A new value, a new secret or a new destination waits for approval. */
  pending: boolean;
  /** A person refused sending it somewhere. */
  refused: boolean;
}

export function decorate(
  rows: readonly SecretRef[],
  waiting: ReadonlySet<string>,
  refused: ReadonlySet<string>,
): SecretItem[] {
  return rows.map((row) => ({
    row,
    short: shortName(row),
    owner: ownerOf(row),
    pending: waiting.has(row.ref) || hasPendingBinding(row),
    refused: refused.has(row.ref),
  }));
}

export function matchesStatus(item: SecretItem, status: SecretStatus): boolean {
  switch (status) {
    case "all":
      return true;
    case "inUse":
      return !item.row.unreferenced;
    case "unused":
      return item.row.unreferenced;
    case "pending":
      return item.pending;
    case "refused":
      return item.refused;
  }
}

function matchesSearch(item: SecretItem, q: string): boolean {
  if (!q) return true;
  return (
    item.row.ref.toLowerCase().includes(q) ||
    item.short.toLowerCase().includes(q) ||
    (item.owner.name?.toLowerCase().includes(q) ?? false)
  );
}

/** The items the search text and the owner type keep — the status is applied after, so its counts stay honest. */
export function searchAndKind(items: SecretItem[], state: SecretListState): SecretItem[] {
  const q = state.q.trim().toLowerCase();
  return items.filter(
    (i) => matchesSearch(i, q) && (state.kind === "all" || i.owner.kind === state.kind),
  );
}

export function statusCounts(items: SecretItem[]): Record<SecretStatus, number> {
  const counts: Record<SecretStatus, number> = {
    all: items.length,
    inUse: 0,
    unused: 0,
    pending: 0,
    refused: 0,
  };
  for (const i of items) {
    if (i.row.unreferenced) counts.unused += 1;
    else counts.inUse += 1;
    if (i.pending) counts.pending += 1;
    if (i.refused) counts.refused += 1;
  }
  return counts;
}

const time = (iso: string | null | undefined) => (iso ? new Date(iso).getTime() || 0 : 0);
const text = (a: string, b: string) => a.localeCompare(b, undefined, { sensitivity: "base" });
const byName = (a: SecretItem, b: SecretItem) =>
  text(a.short, b.short) || text(a.row.ref, b.row.ref);

function compare(a: SecretItem, b: SecretItem, key: NonNullable<SecretListState["sort"]>): number {
  switch (key) {
    case "name":
      return byName(a, b);
    case "usedBy":
      return text(`${a.owner.kind}${a.owner.name ?? ""}`, `${b.owner.kind}${b.owner.name ?? ""}`);
    case "lastUsed":
      return time(a.row.last_used_at) - time(b.row.last_used_at);
    case "created":
      return time(a.row.created_at) - time(b.row.created_at);
  }
}

/** Sorted copy: the chosen column, or waiting for approval first and then by name. */
export function sortItems(items: SecretItem[], state: SecretListState): SecretItem[] {
  const out = [...items];
  const { sort, dir } = state;
  if (!sort) {
    return out.sort((a, b) => Number(b.pending) - Number(a.pending) || byName(a, b));
  }
  const sign = dir === "desc" ? -1 : 1;
  return out.sort((a, b) => sign * compare(a, b, sort) || byName(a, b));
}

/** What a secret's delete is up against: only a stored secret nothing uses and nothing waits on can go. */
export function isDeletable(item: SecretItem): boolean {
  return item.row.unreferenced && item.row.present && !item.pending;
}

export interface OwnerGroup {
  key: string;
  owner: Owner;
  items: SecretItem[];
}

/** Items grouped by owner, in the order the groups first appear; secrets nothing owns come last. */
export function groupByOwner(items: SecretItem[]): OwnerGroup[] {
  const groups = new Map<string, OwnerGroup>();
  for (const item of items) {
    const group = groups.get(item.owner.key);
    if (group) group.items.push(item);
    else groups.set(item.owner.key, { key: item.owner.key, owner: item.owner, items: [item] });
  }
  const all = [...groups.values()];
  return [...all.filter((g) => g.key !== "none"), ...all.filter((g) => g.key === "none")];
}
