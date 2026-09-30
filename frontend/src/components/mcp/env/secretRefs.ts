// src/components/mcp/env/secretRefs.ts — how a stored-secret ref reads in the
// Environment / Headers picker, and which stored secrets a row may cite.
import type { ParsedEnvVar } from "@/lib/mcp/pasteTypes";

/** A Secrets-page secret's ref: `secret/<name>`. */
const SECRET_PREFIX = "secret/";

const secretPageRef = (name: string) => `${SECRET_PREFIX}${name}`;

/** What a ref is called in the picker: a Secrets-page secret by its name, a
 *  ref Coffer minted for this server (`mcp_server/<uid>/<KEY>`) by its key, and
 *  anything else (a ref written by hand) as itself. */
export function refLabel(ref: string): string {
  if (ref.startsWith(SECRET_PREFIX)) return ref.slice(SECRET_PREFIX.length);
  const minted = /^mcp_server\/[0-9a-f]{32}\/(.+)$/.exec(ref);
  return minted ? minted[1] : ref;
}

/** Whether the ref is this row's own stored secret (not a Secrets-page one). */
export const isOwnRef = (row: ParsedEnvVar, ref: string | null | undefined) =>
  !!ref && ref === row.storedRef && !ref.startsWith(SECRET_PREFIX);

/** The refs the row's picker offers: its own stored secret first, then every
 *  Secrets-page secret, then (if it is neither) the ref the row cites now. */
export function pickerRefs(row: ParsedEnvVar, secretNames: readonly string[]): string[] {
  const out: string[] = [];
  if (row.storedRef && !row.storedRef.startsWith(SECRET_PREFIX)) out.push(row.storedRef);
  for (const name of secretNames) out.push(secretPageRef(name));
  if (row.ref && !out.includes(row.ref)) out.push(row.ref);
  return out;
}
