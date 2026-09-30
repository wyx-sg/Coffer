// src/lib/version.ts — how the app writes Coffer's own version in its chrome.
//
// The sidebar footer prints the running daemon's version as "v1.0.0" (design
// ① Shell, ⑥ System). The string is the one `/api/v1/daemon/status` reports —
// the Python package's version — so it names the build that is running and
// changes only when a release bumps it.

/** "v1.0.0" for "1.0.0"; a version already carrying the "v" is left alone. */
export function formatVersion(version: string): string {
  return version.startsWith("v") ? version : `v${version}`;
}
