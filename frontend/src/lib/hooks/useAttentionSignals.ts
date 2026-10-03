// src/lib/hooks/useAttentionSignals.ts — which sidebar entries carry a count badge, and how many.
//
// The web UI owns only the rendering (spec web-ui "Mark a sidebar entry whose
// kind needs attention"); what raises and clears a signal belongs to the
// capability that owns the kind. This is the one per-entry map, keyed by the
// entry's route. An entry absent from it never carries a badge, and a signal
// answers nothing while it has not loaded or its read failed, so the sidebar
// never shows an error.
//
// The sidebar speaks only through counts of things that need the user —
// failures, drift, a held vault — and informational counts never become
// badges (design note n_shell). So:
//
// - Most entries count the daemon's cross-kind attention list (GET
//   /attention, the list Overview's "Needs you" shows) by kind, leaving out
//   `info` items: an agent the user chose not to connect is worth a Needs-you
//   row, not a badge.
// - Sync keeps its own signal, cleared by visiting the page rather than by the
//   situation changing (spec vault-sync "Say a vault needs a human where the
//   user already is"): one situation, so a count of one.
// - CLIs count the required commands (not a tool added by hand that nothing needs) that are missing, too old or not logged
//   in, from the CLIs list itself (the rows the attention list reports as
//   kind `cli`, which is why that kind is not counted twice below).
// - Knowledge has no signal: items waiting in a collection's inbox are the
//   Inbox node's count in the tree, never a sidebar badge (design decision 15).
import { useAttention, type AttentionItem } from "@/lib/hooks/useAttention";
import { useClis } from "@/lib/hooks/useClis";
import { useSyncAttention } from "@/lib/hooks/useSyncAttention";

/** @ui-only derived view; never crosses the wire. */
export interface AttentionSignal {
  count: number;
}

export type AttentionSignals = Readonly<Record<string, AttentionSignal | undefined>>;

/** The attention list's kinds that badge a sidebar entry, and which entry. */
const ENTRY_FOR_KIND: Readonly<Record<string, string>> = {
  agent: "/agents",
  provider: "/model-providers",
  channel: "/channels",
  mcp_server: "/mcp-servers",
  skill: "/skills",
};

/** The attention list re-read on every page; Overview's stream refreshes it sooner. */
const ATTENTION_POLL_MS = 60_000;

/** Count the list's non-informational items per entry. Pure, for tests. */
export function countByEntry(items: readonly AttentionItem[]): Record<string, AttentionSignal> {
  const out: Record<string, AttentionSignal> = {};
  for (const item of items) {
    const entry = ENTRY_FOR_KIND[item.kind];
    if (!entry || item.severity === "info") continue;
    const prev = out[entry];
    out[entry] = { count: (prev?.count ?? 0) + 1 };
  }
  return out;
}

export function useAttentionSignals(): AttentionSignals {
  const attention = useAttention({ refetchInterval: ATTENTION_POLL_MS });
  const sync = useSyncAttention();
  const clis = useClis();
  const signals: Record<string, AttentionSignal | undefined> = attention.data
    ? countByEntry(attention.data.items ?? [])
    : {};
  if (sync) signals["/sync"] = { count: 1 };
  // A tool added by hand that nothing requires is a plain status, not a need.
  const clisNeedingYou = (clis.data?.items ?? []).filter(
    (cli) =>
      cli.status !== "ready" && (cli.needed_by.length > 0 || cli.needed_by_servers.length > 0),
  ).length;
  if (clisNeedingYou > 0) signals["/clis"] = { count: clisNeedingYou };
  return signals;
}
