// src/components/mcp/env/rowsModel.ts — the edit dialog's Environment /
// Headers rows to and from a stored MCP server config.
//
// A config keeps plain values in `transport.env` (stdio) or `transport.headers`
// (HTTP) and secrets in `transport.secret_refs` (KEY → ref). The dialog
// shows both as one list of rows (`ParsedEnvVar`), secrets first. On the way
// back each Secret row either cites a stored secret (its ref goes into
// secret_refs, nothing is written) or carries a typed value (written to
// the keychain first, see `editMcpServerSave.ts`).
import type { TFunction } from "i18next";

import type { ParsedEnvVar } from "@/lib/mcp/pasteTypes";

/** A Secrets-page ref is shared with other resources; never written through. */
const isSecretsPageRef = (ref: string) => ref.startsWith("secret/");

export function secretRefsOf(config: unknown): Record<string, string> {
  const transport = (config as Record<string, unknown> | null)?.transport;
  const refs = (transport as Record<string, unknown> | undefined)?.secret_refs;
  const out: Record<string, string> = {};
  if (refs && typeof refs === "object") {
    for (const [k, v] of Object.entries(refs)) {
      if (typeof v === "string") out[k] = v;
    }
  }
  return out;
}

/** The rows a stored config loads as: each secret ref a Secret row citing
 *  it, then each plain value a Plain row. */
export function rowsOf(config: unknown, plain: { key: string; value: string }[]): ParsedEnvVar[] {
  const secrets = Object.entries(secretRefsOf(config)).map(([key, ref]) => ({
    key,
    value: "",
    isSecret: true,
    ref,
    storedRef: ref,
    loadedKey: key,
  }));
  return [...secrets, ...plain.map((p) => ({ ...p, isSecret: false }))];
}

/** The plain rows as the `env` / `headers` map. */
export function plainMapOf(rows: ParsedEnvVar[]): Record<string, string> {
  return Object.fromEntries(
    rows.filter((r) => !r.isSecret && r.key.trim() !== "").map((r) => [r.key.trim(), r.value]),
  );
}

/** One Secret row with a typed value; `rotate` is the ref it is written
 *  through, or null for a freshly minted one. */
interface TypedSecret {
  key: string;
  value: string;
  rotate: string | null;
}

/** What the Secret rows ask for: refs cited as they are, and typed values. */
export interface SecretPlan {
  cited: Record<string, string>;
  typed: TypedSecret[];
}

/**
 * Sort the Secret rows into cited refs and typed values, refusing what cannot
 * be saved: a row with neither, and a row whose key was renamed while it keeps
 * its own stored secret (the dialog holds no plaintext to re-address it with).
 */
export function secretPlanOf(rows: ParsedEnvVar[], t: TFunction): SecretPlan {
  const plan: SecretPlan = { cited: {}, typed: [] };
  for (const row of rows) {
    const key = row.key.trim();
    if (!row.isSecret || key === "") continue;
    const own = row.storedRef && !isSecretsPageRef(row.storedRef) ? row.storedRef : null;
    const renamed = row.loadedKey !== key;
    if (row.value !== "") {
      // A new value goes through the row's own ref while the key is unchanged
      // (minting on every rotation would move the secret, and a move crosses
      // the sync remote as a delete plus an add); otherwise a fresh address.
      plan.typed.push({ key, value: row.value, rotate: own && !renamed ? own : null });
      continue;
    }
    const ref = row.ref ?? own;
    if (!ref) throw new Error(t("mcp.edit.errSecretNeedsValue", { name: key }));
    if (ref === own && renamed) throw new Error(t("mcp.edit.errRenameNeedsValue", { name: key }));
    plan.cited[key] = ref;
  }
  return plan;
}
