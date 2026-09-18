// frontend/src/lib/credentialRef.ts
// Where a credential ref is minted, for the two kinds that mint one from the
// browser (`channel` and `mcp_server`). The backend's `provider` kind mints its
// own in `application/provider/service.py::_mint_ref`; this is the same shape,
// spelled once so the three call sites here cannot drift from each other.
//
// A ref is an ADDRESS, not a description. Both kinds used to derive it from the
// resource's NAME (`channel/<name>/<secret>`, `<name>.<env key>`), which made
// the name a key: renaming then had to move the secret in the encrypted store,
// in an order chosen so a live agent never saw a missing one. That was
// survivable only while neither kind could be renamed at all. Rename is now a
// field on `PATCH /resources/{uid}` for every kind
// (docs/decisions/resource-identity-is-an-immutable-uid.md), so the derivation
// had to go before the rename that reaches it.
//
// What stays is the trailing logical key — `bot-token`, `SMART_PAT`. It is not
// derived from anything mutable, and it is the only thing that makes a ref
// readable in `coffer credentials list`.

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
export type CredentialRefKind = "channel" | "mcp_server";

/**
 * A fresh vault address for one secret: `<kind>/<uuid4 hex>/<logical key>`.
 *
 * Fresh per SECRET, not per resource — the same rule provider follows. A
 * rotation must therefore reuse the ref already in the config rather than call
 * this again, or the secret moves and crosses the sync remote as a delete plus
 * an unrelated add.
 */
export function mintCredentialRef(kind: CredentialRefKind, logicalKey: string): string {
  return `${kind}/${uuid4Hex()}/${logicalKey}`;
}

/**
 * Whether `ref` is one Coffer minted for `kind` — the replacement for the
 * `<name>.` prefix test that the MCP edit dialog used to decide which
 * no-longer-cited refs it may delete.
 *
 * It answers a narrower question than the old test did, and that is the point:
 * a minted ref carries a uuid nothing else can have produced, so matching the
 * shape means Coffer created this address for one secret of this kind. A ref
 * the user typed themselves, or pasted from elsewhere to share one secret
 * between two servers, cannot match and is never deleted. The old prefix test
 * could not tell those apart — a hand-written `smart.TOKEN` looked exactly like
 * a minted one — and it went wrong the other way too, since renaming the server
 * made every ref it owned stop matching.
 */
export function isMintedCredentialRef(kind: CredentialRefKind, ref: string): boolean {
  return new RegExp(`^${kind}/[0-9a-f]{32}/`).test(ref);
}
