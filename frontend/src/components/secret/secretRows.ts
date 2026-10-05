// src/components/secret/secretRows.ts — pure helpers the Secrets page reads its rows through.
//
// A row is one ref the store holds or a resource cites. A standalone secret
// (`secret/<name>`) is referred to by its `coffer://secret/<name>`; any other ref is its own
// reference. What a row is called is `displayName`. What
// uses a ref is every resource citing it plus every skill whose files cite
// its URI, each with the page it opens (spec web-ui "Manage stored secrets on
// the Secrets page").
import type { Approval, SecretRef } from "@/lib/api/secret";
import { SECRET_PREFIX, isValidSecretName } from "@/lib/secretValue";

export { SECRET_PREFIX, isValidSecretName };

/** The name of a standalone secret, or null for a resource's own ref. */
export function standaloneName(ref: string): string | null {
  if (!ref.startsWith(SECRET_PREFIX)) return null;
  const name = ref.slice(SECRET_PREFIX.length);
  return isValidSecretName(name) ? name : null;
}

/** The most a label and a description can say (spec secret "Label and describe a secret without
 *  changing its reference"). */
export const LABEL_MAX = 64;
export const DESCRIPTION_MAX = 200;

const HEX_ID = /^[0-9a-f]{32}$/i;

/** A minted id (32 hex characters), which is never a name worth showing. */
export function isMintedId(segment: string): boolean {
  return HEX_ID.test(segment);
}

/** What the list calls a secret: its label; else a standalone secret's name; else the first citer's
 *  name and the slot it cites it in; else a legacy ref's short name. A minted hex id is never shown —
 *  `unnamed` stands in when nothing else names it (spec web-ui "Manage stored secrets on the
 *  Secrets page"). */
export function displayName(row: SecretRef, unnamed = "Unnamed secret"): string {
  const label = row.label?.trim();
  if (label) return label;
  const standalone = standaloneName(row.ref);
  if (standalone !== null && !isMintedId(standalone)) return standalone;
  const first = row.cited_by[0];
  const citer = first?.name ?? row.mentioned_by_skills[0];
  // The slot: a resource's own legacy ref ends in it; a `secret/<id>` ref cannot say, so it is read
  // from the binding where the first citer cites it.
  const last = row.ref.split("/").pop() ?? row.ref;
  const fromRef = standalone === null && !isMintedId(last) ? shortName(row) : null;
  const bound = first
    ? row.bindings.find((b) => b.destination_kind === first.kind && b.destination_uid === first.uid)
        ?.slot
    : undefined;
  const slot = fromRef ?? bound ?? null;
  if (citer) return slot ? `${citer} · ${slot}` : citer;
  return slot ?? unnamed;
}

/** The last path segment of a ref; `postman.AUTHORIZATION` drops its owner's name prefix. This is
 *  the name the list shows for a resource's own ref (`mcp_server/<uid>/JIRA_TOKEN`). */
export function shortName(row: SecretRef): string {
  const segments = row.ref.split("/");
  const last = segments[segments.length - 1] || row.ref;
  const dot = last.indexOf(".");
  if (segments.length === 1 && dot > 0) {
    const prefix = last.slice(0, dot).toLowerCase();
    if (row.cited_by.some((c) => c.name.toLowerCase() === prefix)) return last.slice(dot + 1);
  }
  return last;
}

/** The name an approval's secret goes by: the list's short name, else the ref without its namespace. */
export function approvalSecretName(approval: Approval, rows: readonly SecretRef[]): string {
  const row = rows.find((r) => r.ref === approval.ref);
  return row ? shortName(row) : (approval.ref ?? "").replace(SECRET_PREFIX, "");
}

/** What "Copy reference" copies — the URI a file cites, else the ref a resource cites. */
export function referenceOf(row: SecretRef): string {
  return row.uri ?? row.ref;
}

/** One thing that uses a secret, and the page it opens (null: no page of its own). */
export interface Citer {
  key: string;
  kind: string;
  /** The citing resource's uid; empty for a skill that only mentions the URI. */
  uid: string;
  name: string;
  href: string | null;
}

const enc = encodeURIComponent;

/** The page a citer opens: kinds keyed by fixed name use it, the rest their uid. */
export function citerHref(kind: string, name: string, uid: string): string | null {
  switch (kind) {
    case "mcp_server":
      return `/mcp-servers/${enc(name)}`;
    case "skill":
      return `/skills/${enc(name)}`;
    case "provider":
      return `/model-providers/${enc(uid)}`;
    case "channel":
      return `/channels/${enc(uid)}`;
    case "knowledge":
      return `/knowledge/${enc(uid)}`;
    case "memory":
      return `/memory/${enc(uid)}`;
    case "agent":
      // The citer carries the agent's name, not its type, which is what the
      // agent's page is keyed by: open the list it is on.
      return "/agents";
    default:
      return null;
  }
}

/** Every resource citing the ref, then every skill citing its URI not already named. */
export function citersOf(row: SecretRef): Citer[] {
  const out: Citer[] = row.cited_by.map((c) => ({
    key: `${c.kind}:${c.uid}`,
    kind: c.kind,
    uid: c.uid,
    name: c.name,
    href: citerHref(c.kind, c.name, c.uid),
  }));
  const skills = new Set(out.filter((c) => c.kind === "skill").map((c) => c.name));
  for (const skill of row.mentioned_by_skills) {
    if (skills.has(skill)) continue;
    out.push({
      key: `skill:${skill}`,
      kind: "skill",
      uid: "",
      name: skill,
      href: citerHref("skill", skill, ""),
    });
  }
  return out;
}

/** Whether a destination citing the ref waits for approval before it gets it. */
export function hasPendingBinding(row: SecretRef): boolean {
  return row.bindings.some((b) => b.status === "pending");
}

/** Cited but not stored here, or stored but unopenable with this Mac's master
 *  key: either way this Mac has no value to hand out (spec secret "Show a
 *  secret this Mac cannot open as missing on this Mac"). */
export function isMissingHere(row: SecretRef): boolean {
  return !row.present || row.locked;
}

/** The citers a `409 SECRET_IN_USE` names (`details.resources`), as citers. */
export function citersFromRefusal(details: unknown): Citer[] {
  const resources =
    details && typeof details === "object" && "resources" in details
      ? (details as { resources?: unknown }).resources
      : undefined;
  if (!Array.isArray(resources)) return [];
  return resources.flatMap((r: unknown) => {
    if (!r || typeof r !== "object") return [];
    const { kind, name, uid } = r as { kind?: unknown; name?: unknown; uid?: unknown };
    if (typeof kind !== "string" || typeof name !== "string") return [];
    const id = typeof uid === "string" ? uid : "";
    return [{ key: `${kind}:${id || name}`, kind, uid: id, name, href: citerHref(kind, name, id) }];
  });
}
