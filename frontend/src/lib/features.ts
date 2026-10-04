// src/lib/features.ts — the four experimental features the web UI knows by name.
//
// The daemon's registry decides which features exist and what state each is in
// (spec experimental-features); this file is the web UI's half: the keys, and —
// through the `feature` field of the entries in `lib/navigation.ts` — which
// sidebar entries and pages each one owns. Every feature is off until the user
// switches it on in Settings → Features. The display name and the one-line
// description of a key live in the locale files under `settings.features.names`
// / `.descriptions`.

/** The four experimental features, in registry order. */
export type FeatureKey = "knowledge" | "memory" | "sync" | "models";

/** The feature that owns the page of a resource kind (an audit entry's
 *  `resource_kind`, a secret citer's `kind`); a kind not listed is always on. */
const FEATURE_OF_KIND: Readonly<Record<string, FeatureKey>> = {
  provider: "models",
  knowledge: "knowledge",
  memory: "memory",
};

export function featureOfKind(kind: string): FeatureKey | undefined {
  return FEATURE_OF_KIND[kind];
}
