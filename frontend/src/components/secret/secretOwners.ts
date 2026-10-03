// src/components/secret/secretOwners.ts — a secret's short name and who owns it, read off its ref and its citers.
//
// A resource's ref is an address (`mcp_server/<uid>/JIRA_PERSONAL_TOKEN`), unreadable at a
// glance: the list shows its last segment as the name and says the owner in words ("MCP
// server · jira"), the owner's name coming from the citers the API already returns.
import type { SecretRef } from "@/lib/api/secret";
import type { OwnerKind } from "@/lib/secrets/listState";
import { OWNER_KINDS } from "@/lib/secrets/listState";

export interface Owner {
  /** Groups the secrets one owner has; `none` is every secret nothing owns. */
  key: string;
  kind: OwnerKind;
  /** The owner's own name; null when only its kind is known. */
  name: string | null;
  /** Further citers beyond the first. */
  more: number;
}

/** The owner kind a citer's kind (or a ref's first segment) falls under. */
function ownerKindOf(kind: string): OwnerKind {
  if (kind === "sync_remote") return "sync";
  return (OWNER_KINDS as readonly string[]).includes(kind) && kind !== "other"
    ? (kind as OwnerKind)
    : "other";
}

/** The last path segment of a ref; `postman.AUTHORIZATION` drops its owner's name prefix. */
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

export function ownerOf(row: SecretRef): Owner {
  const first = row.cited_by[0];
  if (first) {
    return {
      key: `${first.kind}:${first.uid}`,
      kind: ownerKindOf(first.kind),
      name: first.name,
      more: row.cited_by.length - 1,
    };
  }
  const skill = row.mentioned_by_skills[0];
  if (skill) {
    return {
      key: `skill:${skill}`,
      kind: "other",
      name: skill,
      more: row.mentioned_by_skills.length - 1,
    };
  }
  const prefix = row.ref.includes("/") ? row.ref.split("/")[0] : "";
  return { key: "none", kind: ownerKindOf(prefix), name: null, more: 0 };
}
