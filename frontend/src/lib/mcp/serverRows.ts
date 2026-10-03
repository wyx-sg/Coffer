// frontend/src/lib/mcp/serverRows.ts — a server's Environment / Headers as the
// shared header / env rows (components/secret/KeyValueSecretRows), and back to a
// stored config.
//
// Secrets live only in Coffer (principle 22): a row's value is plain text, a
// stored secret, or a new one written to Secrets when the form is submitted. A
// config keeps plain values in `transport.env` (stdio) or `transport.headers`
// (HTTP) and a chosen secret in `transport.secret_refs` as `secret/<name>`.
import {
  defaultSecretName,
  secretNameOf,
  secretRef,
  type KeyValueSecretRow,
} from "@/lib/secretValue";
import type { ParsedEnvVar } from "./pasteTypes";

/** The name a ref is called in the picker: a Secrets-page secret by its name, a
 *  ref Coffer minted for the server (`mcp_server/<uid>/<KEY>`) by its key. */
function refLabel(ref: string): string {
  const named = secretNameOf(ref);
  if (named) return named;
  const minted = /^mcp_server\/[0-9a-f]{32}\/(.+)$/.exec(ref);
  return minted ? minted[1] : ref;
}

/** The keys that arrived flagged secret without a value (a
 *  `bearer_token_env_var` header): the person has to supply one. */
export const askedKeysOf = (env: readonly ParsedEnvVar[]): Set<string> =>
  new Set(env.filter((e) => e.isSecret && e.value === "" && !e.ref).map((e) => e.key));

/** A pasted / imported pair as a row. A pair flagged secret becomes a new
 *  secret named from its key (unique among `taken`, which grows); a plain pair
 *  stays plain; a flagged pair without a value waits for one — as a new secret
 *  with no value (the review's password box), or with `askAsPlain` (the form)
 *  as an empty plain row the person types into (see `promoteAsked`). */
export function rowsFromParsed(
  env: ParsedEnvVar[],
  taken: Set<string>,
  askAsPlain = false,
): KeyValueSecretRow[] {
  return env.map((e) => {
    if (!e.isSecret || (askAsPlain && e.value === "" && !e.ref)) {
      return { key: e.key, value: { kind: "plain", value: e.value } };
    }
    if (e.ref) return { key: e.key, value: { kind: "stored", name: refLabel(e.ref) } };
    const name = defaultSecretName(e.key, taken);
    taken.add(name);
    return { key: e.key, value: { kind: "new", name, value: e.value } };
  });
}

/** Rows for keys that were asked for (see `askedKeysOf`) and are now typed in as
 *  plain text become new secrets, so what was flagged secret never lands in the
 *  config as plain text. */
export function promoteAsked(
  rows: readonly KeyValueSecretRow[],
  asked: ReadonlySet<string>,
  taken: ReadonlySet<string>,
): KeyValueSecretRow[] {
  const used = new Set(taken);
  for (const r of rows) if (r.value.kind === "new") used.add(r.value.name);
  return rows.map((r) => {
    const key = r.key.trim();
    if (!asked.has(key) || r.value.kind !== "plain" || r.value.value === "") return r;
    const name = defaultSecretName(key, used);
    used.add(name);
    return { ...r, value: { kind: "new", name, value: r.value.value } };
  });
}

/** The keys of rows that hold a new secret still without a value. */
export function missingSecretKeys(rows: readonly KeyValueSecretRow[]): string[] {
  return rows
    .filter((r) => r.key.trim() !== "" && r.value.kind === "new" && r.value.value === "")
    .map((r) => r.key);
}

/** The rows that count: a row with no key is a blank line. */
export const keptRows = (rows: readonly KeyValueSecretRow[]) =>
  rows.filter((r) => r.key.trim() !== "");

/** The plain rows as the `env` / `headers` map. */
export function plainMapOfRows(rows: readonly KeyValueSecretRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of keptRows(rows)) if (r.value.kind === "plain") out[r.key.trim()] = r.value.value;
  return out;
}

/** The chosen secrets (stored or new) as `secret_refs`: KEY → `secret/<name>`. */
export function secretRefsOfRows(rows: readonly KeyValueSecretRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of keptRows(rows)) {
    if (r.value.kind !== "plain") out[r.key.trim()] = secretRef(r.value.name);
  }
  return out;
}

/** The chosen secrets of an existing server as `secret_refs`. A stored choice
 *  that is still the secret an older server holds under its own ref (Coffer
 *  minted it for the key) keeps that ref; every other choice is `secret/<name>`. */
export function secretRefsForSave(
  rows: readonly KeyValueSecretRow[],
  original: Record<string, string>,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of keptRows(rows)) {
    if (r.value.kind === "plain") continue;
    const key = r.key.trim();
    const was = original[key];
    const keeps =
      r.value.kind === "stored" &&
      was !== undefined &&
      secretNameOf(was) === null &&
      refLabel(was) === r.value.name;
    out[key] = keeps ? was : secretRef(r.value.name);
  }
  return out;
}

function refsOf(config: unknown): Record<string, string> {
  const transport = (config as Record<string, unknown> | null)?.transport;
  const refs = (transport as Record<string, unknown> | undefined)?.secret_refs;
  const out: Record<string, string> = {};
  if (refs && typeof refs === "object") {
    for (const [k, v] of Object.entries(refs)) if (typeof v === "string") out[k] = v;
  }
  return out;
}

/** The refs a stored config cites, by key. */
export const secretRefsOf = refsOf;

/** The rows a stored config loads as: each cited secret as a stored choice,
 *  then each plain value. */
export function rowsOf(config: unknown, plain: { key: string; value: string }[]) {
  const secrets: KeyValueSecretRow[] = Object.entries(refsOf(config)).map(([key, ref]) => ({
    key,
    value: { kind: "stored", name: refLabel(ref) },
  }));
  const plains: KeyValueSecretRow[] = plain.map((p) => ({
    key: p.key,
    value: { kind: "plain", value: p.value },
  }));
  return [...secrets, ...plains];
}
