// src/lib/overview/attention.ts — the "Needs you" list's order, and where each item's name and action lead.
//
// Pure: the Overview's rows are the daemon's attention items (spec
// resource-framework "Report what needs a person across every kind") sorted
// most severe first, then oldest first, and each row links to the page where
// the person can act on it. The action's `method`/`path` name a daemon route,
// not a page, so the page is chosen here from the item's kind and reason.
import type { AttentionItem } from "@/lib/hooks/useAttention";
import type { StatusTone } from "@/components/status/statusTone";

type Severity = AttentionItem["severity"];

const SEVERITY_RANK: Record<Severity, number> = { error: 0, warning: 1, info: 2 };

function sinceTime(item: AttentionItem): number | null {
  if (!item.since) return null;
  const ms = Date.parse(item.since);
  return Number.isNaN(ms) ? null : ms;
}

/** Most severe first, then the oldest `since` first; an item with no `since` goes last. */
export function sortAttention(items: readonly AttentionItem[]): AttentionItem[] {
  return [...items].sort((a, b) => {
    const bySeverity = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
    if (bySeverity !== 0) return bySeverity;
    const sa = sinceTime(a);
    const sb = sinceTime(b);
    if (sa === sb) return 0;
    if (sa === null) return 1;
    if (sb === null) return -1;
    return sa - sb;
  });
}

/** The dot a row carries: red for an error, amber for everything else. */
export function severityTone(severity: Severity): StatusTone {
  return severity === "error" ? "err" : "warn";
}

/** Each kind's list page, and the detail page an item with a uid opens. */
const PAGES: Record<string, { list: string; detail?: (uid: string) => string }> = {
  agent: { list: "/agents", detail: (uid) => `/agents/${uid}` },
  // The detail route is keyed by name; a uid address redirects to it.
  mcp_server: { list: "/mcp-servers", detail: (uid) => `/mcp-servers/${uid}` },
  skill: { list: "/skills", detail: (uid) => `/skills/${uid}` },
  channel: { list: "/channels", detail: (uid) => `/channels/${uid}` },
  provider: { list: "/model-providers", detail: (uid) => `/model-providers/${uid}` },
  knowledge: { list: "/knowledge", detail: (uid) => `/knowledge/${uid}` },
  memory: { list: "/memory", detail: (uid) => `/memory/${uid}` },
  sync: { list: "/sync" },
  // A target the reconciler could not check is written up in the daemon log.
  reconcile: { list: "/activity?tab=daemon" },
};

const encode = encodeURIComponent;

/** The page an item's name opens: its detail page, its kind's list, or Activity. */
export function itemPage(item: AttentionItem): string {
  const page = PAGES[item.kind];
  if (!page) return "/activity";
  return item.uid && page.detail ? page.detail(encode(item.uid)) : page.list;
}

/** The page an item's one action opens — a missing secret is added on Secrets. */
export function actionPage(item: AttentionItem): string {
  if (item.reason_code === "mcp_missing_secret") return "/secrets";
  return itemPage(item);
}

const VERBS = new Set(["connect", "test", "set_secret", "check", "run", "review", "repair"]);

/** i18n key of the action button's label; an unknown verb reads "Open". */
export function actionLabelKey(verb: string): string {
  return `overview.actions.${VERBS.has(verb) ? verb : "open"}`;
}
