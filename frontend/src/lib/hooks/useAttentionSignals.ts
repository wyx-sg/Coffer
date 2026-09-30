// src/lib/hooks/useAttentionSignals.ts — which sidebar entries carry the attention dot.
//
// The web UI owns only the rendering (spec web-ui "Mark a sidebar entry whose
// kind needs attention"); what raises and clears a signal belongs to the
// capability that owns the kind. This is the one per-entry map: a kind that
// declares a signal adds its hook here, keyed by its entry's route, and the
// sidebar marks it with the same dot and no other change. An entry absent from
// the map never carries a dot, and each signal answers `false` while it has
// not loaded or its read failed, so the sidebar never shows an error.
//
// Two signals today: Sync's (spec vault-sync "Say a vault needs a human where
// the user already is"), cleared by visiting the page, and the CLIs entry's,
// raised while any required command is missing, too old or not logged in (the
// rows the attention list reports as kind `cli`) and cleared by fixing them.
import { useClisAttention } from "@/lib/hooks/useClis";
import { useSyncAttention } from "@/lib/hooks/useSyncAttention";

export type AttentionSignals = Readonly<Record<string, boolean>>;

export function useAttentionSignals(): AttentionSignals {
  const sync = useSyncAttention();
  const clis = useClisAttention();
  return { "/sync": sync, "/clis": clis };
}
