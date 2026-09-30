// src/lib/customTools/drafts.ts — what the group forms hold, and the request bodies they send.
import type {
  CustomTool,
  CustomToolAuthIn,
  CustomToolGroup,
  CustomToolIn,
} from "@/lib/api/customTools";

/** A group name: lowercase, digits and `-`, up to 24 characters. */
const GROUP_NAME_RE = /^[a-z0-9][a-z0-9-]{0,23}$/;

export function isGroupName(name: string): boolean {
  return GROUP_NAME_RE.test(name);
}

/** The auth header as a group form holds it. */
export interface AuthDraft {
  header: string;
  prefix: string;
  secret: string | null;
}

export const DEFAULT_AUTH: AuthDraft = { header: "Authorization", prefix: "Bearer", secret: null };

/** A prefix ending in a word gets the space before the value ("Bearer "). */
function normalisedPrefix(prefix: string): string {
  const trimmed = prefix.trimStart();
  if (trimmed === "") return "";
  return /[A-Za-z0-9]$/.test(trimmed) ? `${trimmed} ` : trimmed;
}

/** The request's auth: bound to a secret, or none at all. */
export function authBody(draft: AuthDraft): CustomToolAuthIn | null {
  if (!draft.secret) return null;
  return {
    header: draft.header.trim() || "Authorization",
    prefix: normalisedPrefix(draft.prefix),
    secret: draft.secret,
  };
}

/** A group's stored auth, back into the form. */
export function authDraftOf(group: CustomToolGroup): AuthDraft {
  if (!group.auth) return { ...DEFAULT_AUTH };
  return { header: group.auth.header, prefix: group.auth.prefix.trim(), secret: group.auth.secret };
}

/** "Authorization: Bearer" — how an auth header reads before its secret. */
export function authLine(header: string, prefix: string): string {
  const p = prefix.trim();
  return p ? `${header}: ${p}` : `${header}:`;
}

/** A saved tool as the draft its editor starts from. */
export function draftOf(tool: CustomTool): CustomToolIn {
  return {
    name: tool.name,
    description: tool.description,
    method: tool.method,
    path: tool.path,
    headers: { ...tool.headers },
    body_template: tool.body_template,
    input_schema: tool.input_schema,
    enabled: tool.enabled,
    changes_data: tool.changes_data,
    operation: tool.operation,
  };
}

export function emptyDraft(): CustomToolIn {
  return {
    name: "",
    description: "",
    method: "GET",
    path: "/",
    headers: {},
    body_template: null,
    input_schema: { type: "object", properties: {} },
    enabled: true,
    changes_data: false,
  };
}
