// src/components/settings/security/fingerprint.ts — how a master key fingerprint reads.
//
// The daemon's fingerprint is 12 lowercase hex characters (the one every
// machine publishes in its sync descriptor). People compare it across two
// screens, so it is shown uppercase in groups of four: `7F3A 91C2 5D0E`.

/** `7f3a91c25d0e` → `7F3A 91C2 5D0E`. */
export function formatFingerprint(fingerprint: string): string {
  return (fingerprint.toUpperCase().match(/.{1,4}/g) ?? []).join(" ");
}

/** A path under a home folder, as `~/…`, the way the design names folders. */
export function tildePath(path: string): string {
  return path.replace(/^\/(?:Users|home)\/[^/]+(?=\/|$)/, "~");
}

/** The name a stored secret is shown under: a standalone `secret/<name>` by its name. */
export function secretName(ref: string): string {
  return ref.startsWith("secret/") ? ref.slice("secret/".length) : ref;
}
