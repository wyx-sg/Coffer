// frontend/src/lib/secretRef.ts
// Where a secret's id is minted in the browser. Every secret is `secret/<uuid4 hex>`: the ref is an
// ADDRESS, not a description, so nothing in it comes from a resource's name, its kind or the slot
// that cites it — those change, the id never does. What a person calls the secret is its label, and
// what cites it is read from the list (spec secret "Label and describe a secret without changing
// its reference").

/** A uuid4 as 32 hex characters, the spelling `machine_id` and provider refs
 *  already use.
 *
 *  Built from `getRandomValues` rather than `crypto.randomUUID`, which is only
 *  defined in a secure context — Coffer's UI is normally on http://localhost
 *  (which counts), but a vault reached over a LAN address is plain http and
 *  would hand us `undefined` at the exact moment a user is storing a secret.
 *  The two masked bytes are the version and variant bits, so the value really
 *  is a v4 UUID and not merely 16 random bytes wearing its shape. */
export function uuid4Hex(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * A fresh vault address for one secret: `secret/<uuid4 hex>`.
 *
 * Fresh per SECRET, not per resource. A rotation must therefore reuse the ref already in the config
 * rather than call this again, or the secret moves and crosses the sync remote as a delete plus an
 * unrelated add.
 */
export function mintSecretRef(): string {
  return `secret/${uuid4Hex()}`;
}
