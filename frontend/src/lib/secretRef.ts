// frontend/src/lib/secretRef.ts
// Where a secret ref is minted, for the two kinds that mint one from the
// browser (`channel` and `mcp_server`). The backend's `provider` kind mints its
// own in `application/provider/service.py::_mint_ref`; this is the same shape,
// spelled once so the three call sites here cannot drift from each other.
//
// A ref is an ADDRESS, not a description: nothing in it comes from the
// resource's name, because rename is a field on `PATCH /resources/{uid}` for
// every kind (docs/decisions/resource-identity-is-an-immutable-uid.md) and a
// name-derived ref would make the name a key into the encrypted store.
//
// The trailing logical key — `bot-token`, `SMART_PAT`. It is not
// derived from anything mutable, and it is the only thing that makes a ref
// readable in `coffer secret list`.

/** A uuid4 as 32 hex characters, the spelling `machine_id` and provider refs
 *  already use.
 *
 *  Built from `getRandomValues` rather than `crypto.randomUUID`, which is only
 *  defined in a secure context — Coffer's UI is normally on http://localhost
 *  (which counts), but a vault reached over a LAN address is plain http and
 *  would hand us `undefined` at the exact moment a user is storing a secret.
 *  The two masked bytes are the version and variant bits, so the value really
 *  is a v4 UUID and not merely 16 random bytes wearing its shape. */
function uuid4Hex(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** The kinds that mint their own refs from this file. */
export type SecretRefKind = "channel" | "mcp_server";

/**
 * A fresh vault address for one secret: `<kind>/<uuid4 hex>/<logical key>`.
 *
 * Fresh per SECRET, not per resource — the same rule provider follows. A
 * rotation must therefore reuse the ref already in the config rather than call
 * this again, or the secret moves and crosses the sync remote as a delete plus
 * an unrelated add.
 */
export function mintSecretRef(kind: SecretRefKind, logicalKey: string): string {
  return `${kind}/${uuid4Hex()}/${logicalKey}`;
}

/**
 * Whether `ref` is one Coffer minted for `kind` — what the MCP edit dialog
 * reads to decide which no-longer-cited refs it may delete.
 *
 * A minted ref carries a uuid nothing else can have produced, so matching the
 * shape means Coffer created this address for one secret of this kind. A ref
 * the user typed themselves, or pasted from elsewhere to share one secret
 * between two servers, cannot match and is never deleted.
 */
export function isMintedSecretRef(kind: SecretRefKind, ref: string): boolean {
  return new RegExp(`^${kind}/[0-9a-f]{32}/`).test(ref);
}
