// src/lib/authScheme.ts — the auth scheme of an HTTP header that holds a secret. The secret holds
// only the credential (the raw key a provider hands out); Coffer puts the scheme in front of it
// when it sends: `Authorization: Bearer <key>`. A header with no scheme sends its secret as is.
import { mintSecretName, type KeyValueSecretRow, type RowValue } from "@/lib/secretValue";

export type AuthScheme = "Bearer" | "Token";

export const AUTH_SCHEMES: readonly AuthScheme[] = ["Bearer", "Token"];

const LEADING_SCHEME = /^(Bearer|Token)\s+(\S[\s\S]*)$/i;

/** `Bearer abc` → the scheme and the credential after it; null when `value` has no scheme. */
export function splitScheme(value: string): { scheme: AuthScheme; rest: string } | null {
  const m = LEADING_SCHEME.exec(value.trim());
  if (!m) return null;
  return { scheme: m[1].toLowerCase() === "bearer" ? "Bearer" : "Token", rest: m[2].trim() };
}

/** `value` without a leading `<scheme> ` (any case) — what a person typing the whole header value
 *  into a row that already names the scheme would otherwise send twice. */
export function stripScheme(value: string, scheme: AuthScheme | null | undefined): string {
  if (!scheme) return value;
  const split = splitScheme(value);
  return split && split.scheme === scheme ? split.rest : value;
}

/** The scheme a new secret on a header called `key` starts with. */
export const defaultSchemeFor = (key: string): AuthScheme | null =>
  key.trim().toLowerCase() === "authorization" ? "Bearer" : null;

/** The scheme a row sends: none on a plain row; a secret row's own choice (`null` = None), or the
 *  default for its key while the person has not chosen. */
export function schemeOfRow(row: KeyValueSecretRow): AuthScheme | null {
  if (row.value.kind === "plain") return null;
  return row.scheme === undefined ? defaultSchemeFor(row.key) : row.scheme;
}

/** A new secret's value without the scheme the row already names. */
function stripNew(value: RowValue, scheme: AuthScheme | null): RowValue {
  return value.kind === "new" ? { ...value, value: stripScheme(value.value, scheme) } : value;
}

/** The row with `scheme` chosen; a new secret that typed the scheme into its value loses it there. */
export function withScheme(row: KeyValueSecretRow, scheme: AuthScheme | null): KeyValueSecretRow {
  return { ...row, scheme, value: stripNew(row.value, scheme) };
}

/** A plain row stored as a new secret named `label`. For an HTTP header (`schemes`), a value that
 *  starts with a scheme splits into scheme + credential; otherwise the row's own scheme (or the
 *  key's default) is stripped off what was typed. */
export function storePlainRow(
  row: KeyValueSecretRow,
  label: string,
  schemes = true,
): KeyValueSecretRow {
  const typed = row.value.kind === "plain" ? row.value.value : "";
  const fresh = (value: string) => ({ kind: "new" as const, name: mintSecretName(), label, value });
  if (!schemes) return { ...row, value: fresh(typed) };
  const split = splitScheme(typed);
  const scheme = split
    ? split.scheme
    : row.scheme === undefined
      ? defaultSchemeFor(row.key)
      : row.scheme;
  return { ...row, scheme, value: fresh(split ? split.rest : stripScheme(typed, scheme)) };
}
