// frontend/src/lib/secretRef.ts
// Where a secret ref is minted, for the two kinds that mint one from the
// browser (`channel` and `mcp_server`). The backend's `domain/secrets.py` has
// the same rule for `provider` and for plaintext import; this is its mirror,
// spelled once so the call sites here cannot drift from each other.
//
// A ref is named after the resource and the slot it fills:
// `<kind>/<name segment>/<slot>`, so `coffer secret list` reads as whose secret
// each one is. The name segment is the resource's name with every character
// outside `[A-Za-z0-9_.-]` replaced by `-` and leading dots stripped (never
// empty — it falls back to `x`).
//
// A name is only a label the ref was minted from, never a key to look it up
// by: the config cites the ref, so nothing resolves a secret from the name.
// MCP server names are fixed, so their refs never move; renaming a channel or
// provider moves its refs server-side, in the same change as the rename.

/** The kinds that mint their own refs from this file. */
export type SecretRefKind = "channel" | "mcp_server";

/** A resource name as one ref path segment. Mirrors `ref_segment` in
 *  `domain/secrets.py`. */
export function refSegment(name: string): string {
  const segment = name.replace(/[^A-Za-z0-9_.-]/g, "-").replace(/^\.+/, "");
  return segment === "" ? "x" : segment;
}

/**
 * A vault address for one secret: `<kind>/<name segment>/<slot>`.
 *
 * One per SECRET, not per resource. A rotation must reuse the ref already in
 * the config rather than call this again, or the secret moves and crosses the
 * sync remote as a delete plus an unrelated add.
 */
export function mintSecretRef(kind: SecretRefKind, resourceName: string, slot: string): string {
  return `${kind}/${refSegment(resourceName)}/${slot}`;
}

/**
 * Whether `ref` is named for THIS resource — what the MCP edit dialog reads to
 * decide which no-longer-cited refs it may delete.
 *
 * It matches the resource's own segment, with the `-<n>` suffix the backend
 * adds when two names collapse to one segment. A ref the user typed themselves,
 * or pasted from elsewhere to share one secret between two servers, names some
 * other resource and is never deleted.
 */
export function isOwnRef(kind: SecretRefKind, resourceName: string, ref: string): boolean {
  const segment = refSegment(resourceName).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^${kind}/${segment}(-\\d+)?/`).test(ref);
}
