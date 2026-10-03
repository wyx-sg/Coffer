// src/components/secret/secretRows.ts — pure helpers the Secrets page reads its rows through.
//
// A row is one ref the store holds or a resource cites. A standalone secret
// (`secret/<name>`) shows its name and is referred to by its
// `coffer://secret/<name>`; any other ref is its own name and reference. What
// uses a ref is every resource citing it plus every skill whose files cite
// its URI, each with the page it opens (spec web-ui "Manage stored secrets on
// the Secrets page").
import type { Approval, SecretRef } from "@/lib/api/secret";
import { SECRET_PREFIX, isValidSecretName } from "@/lib/secretValue";

export { SECRET_PREFIX, isValidSecretName };


/** The name of a standalone secret, or null for a resource's own ref. */
function standaloneName(ref: string): string | null {
  if (!ref.startsWith(SECRET_PREFIX)) return null;
  const name = ref.slice(SECRET_PREFIX.length);
  return isValidSecretName(name) ? name : null;
}

/** What the Name column shows: a standalone secret's name, else the ref. */
export function displayName(row: SecretRef): string {
  return standaloneName(row.ref) ?? row.ref;
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
  name: string;
  href: string | null;
}

const enc = encodeURIComponent;

/** The page a citer opens: kinds keyed by fixed name use it, the rest their uid. */
function citerHref(kind: string, name: string, uid: string): string | null {
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
    name: c.name,
    href: citerHref(c.kind, c.name, c.uid),
  }));
  const skills = new Set(out.filter((c) => c.kind === "skill").map((c) => c.name));
  for (const skill of row.mentioned_by_skills) {
    if (skills.has(skill)) continue;
    out.push({
      key: `skill:${skill}`,
      kind: "skill",
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

/** The refs whose new value, or whose adding, waits for approval. */
export function refsWaiting(approvals: readonly Approval[] | undefined): Set<string> {
  const out = new Set<string>();
  for (const a of approvals ?? []) {
    if ((a.op === "replace_value" || a.op === "add_secret") && a.ref) out.add(a.ref);
  }
  return out;
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
    return [{ key: `${kind}:${id || name}`, kind, name, href: citerHref(kind, name, id) }];
  });
}
