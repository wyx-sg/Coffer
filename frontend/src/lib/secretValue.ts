// src/lib/secretValue.ts — the value model of a secret field and of a
// header / env row, plus the pure helpers around it (principle 22: a secret
// lives only in Coffer's Secrets; a form picks one or makes one).
//
// Nothing here knows how a consumer stores the choice: MCP keeps `secret/<name>`
// in `transport.secret_refs`, a custom-tool group keeps the bare name. Use
// `secretRef` / `secretUri` / `secretNameOf` to convert at the edge.
import { secretsApi } from "@/lib/api/secret";
import { uuid4Hex } from "@/lib/secretRef";

/** The store namespace standalone secrets live under. */
export const SECRET_PREFIX = "secret/";

/** One segment of letters, digits, `.`, `_` and `-`, at most 64 characters
 *  (spec secret "Resolve standalone secrets into one child with coffer run"). */
const NAME_RE = /^[A-Za-z0-9_.-]{1,64}$/;

export function isValidSecretName(name: string): boolean {
  return NAME_RE.test(name) && name !== "." && name !== "..";
}

/** A secret chosen from, or about to be added to, the Secrets page. */
type SecretChoice =
  | { kind: "stored"; name: string }
  /** Pasted or typed: written to Secrets when the form is submitted. */
  | {
      kind: "new";
      /** The minted id (32 hex characters) it will be stored under; never typed by a person. */
      name: string;
      /** What the person calls it; stored as the secret's label. */
      label: string;
      value: string;
    };

/** What a secret field holds; null = nothing chosen yet. */
export type SecretFieldValue = SecretChoice | null;

/** What a header / env row's value holds: plain text, or a secret. */
export type RowValue = { kind: "plain"; value: string } | SecretChoice;

export interface KeyValueSecretRow {
  key: string;
  value: RowValue;
}

/** The store ref of a standalone secret: `secret/<name>`. */
export const secretRef = (name: string) => `${SECRET_PREFIX}${name}`;

/** The name inside `secret/<name>` or `coffer://secret/<name>`; null for any other ref. */
export function secretNameOf(ref: string): string | null {
  const bare = ref.startsWith("coffer://") ? ref.slice("coffer://".length) : ref;
  if (!bare.startsWith(SECRET_PREFIX)) return null;
  const name = bare.slice(SECRET_PREFIX.length);
  return isValidSecretName(name) ? name : null;
}

/** How a ref is shown and cited: a standalone secret's `coffer://secret/<name>`,
 *  any other ref as itself (the Secrets page's rule). */
export function secretReferenceOf(ref: string): string {
  const name = secretNameOf(ref);
  return name === null ? ref : `coffer://secret/${name}`;
}

/** A fresh id for a secret that is stored when the form is saved: the 32 hex characters of
 *  `secret/<id>`, the same shape the daemon mints for the Add secret dialog. */
export const mintSecretName = uuid4Hex;

const SECRET_KEY = /token|key|secret|password|passwd|auth|credential/i;

/** Whether a plain value looks like a secret: the key's name says so, or the
 *  value is long and high-entropy (the one-time "Store it in Coffer?" hint). */
export function looksLikeSecret(key: string, value: string): boolean {
  const v = value.trim();
  if (v === "" || /^\$\{?\w+\}?$/.test(v)) return false;
  if (SECRET_KEY.test(key)) return true;
  if (v.length < 20 || /\s/.test(v) || /^[a-z]+:\/\//i.test(v)) return false;
  const classes = [/[a-z]/, /[A-Z]/, /\d/].filter((re) => re.test(v)).length;
  return classes >= 2 && new Set(v).size >= 10;
}

/** The new secrets among `values` — what a form must write on submit. */
function newSecretsOf(
  values: readonly (SecretFieldValue | RowValue)[],
): Extract<SecretChoice, { kind: "new" }>[] {
  const seen = new Map<string, Extract<SecretChoice, { kind: "new" }>>();
  for (const v of values) if (v?.kind === "new") seen.set(v.name, v);
  return [...seen.values()];
}

/**
 * Write every `new` secret among `values` to Secrets (call on submit, before
 * saving the form). Resolves the names written. Rejects on the first failed
 * write.
 */
export async function persistNewSecrets(
  values: readonly (SecretFieldValue | RowValue)[],
): Promise<{ names: string[] }> {
  const names: string[] = [];
  for (const v of newSecretsOf(values)) {
    const ref = secretRef(v.name);
    await secretsApi.set(ref, v.value);
    // The label is a nicety: the secret is stored and cited either way, so a failure to save it
    // must not fail the form that already wrote the value.
    const label = v.label?.trim();
    if (label) {
      try {
        await secretsApi.setNotes(ref, { label });
      } catch (e) {
        console.warn(`[persistNewSecrets] could not label ${ref}:`, e);
      }
    }
    names.push(v.name);
  }
  return { names };
}
