// src/lib/overview/attention.ts — the "Needs you" list's order, and where each item's name and action lead.
//
// Pure: the Overview's rows are the daemon's attention items (spec
// resource-framework "Report what needs a person across every kind") sorted
// most severe first, then oldest first, and each row links to the page where
// the person can act on it. The action's `method`/`path` name a daemon route,
// not a page, so the page is chosen here from the item's kind and reason.
import type { AttentionItem } from "@/lib/hooks/useAttention";
import type { StatusTone } from "@/lib/statusTone";

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

/** What names an item's detail page: its uid, its title (a skill's or an MCP
 *  server's fixed name) and — for an agent, whose pages are addressed by its
 *  type — the type, which the item does not carry: the caller looks it up in
 *  the agent list (`undefined` while unknown). */
interface Address {
  uid: string;
  title: string;
  agentType: string | undefined;
}

const encode = encodeURIComponent;

/** Each kind's list page, and the detail page an item with a uid opens. A
 *  detail address follows the route table (router.tsx): skills and MCP servers
 *  by their fixed name, agents by type, every other kind by uid. */
const PAGES: Record<string, { list: string; detail?: (a: Address) => string | null }> = {
  agent: {
    list: "/agents",
    detail: (a) => (a.agentType ? `/agents/${encode(a.agentType)}` : null),
  },
  mcp_server: { list: "/mcp-servers", detail: (a) => `/mcp-servers/${encode(a.title)}` },
  skill: { list: "/skills", detail: (a) => `/skills/${encode(a.title)}` },
  channel: { list: "/channels", detail: (a) => `/channels/${encode(a.uid)}` },
  provider: { list: "/model-providers", detail: (a) => `/model-providers/${encode(a.uid)}` },
  knowledge: { list: "/knowledge", detail: (a) => `/knowledge/${encode(a.uid)}` },
  memory: { list: "/memory", detail: (a) => `/memory/${encode(a.uid)}` },
  sync: { list: "/sync" },
  // A target the reconciler could not check is written up in the daemon log.
  reconcile: { list: "/activity?tab=daemon" },
  // A command a skill requires is addressed by the command itself.
  cli: { list: "/clis", detail: (a) => `/clis/${encode(a.uid)}` },
};

/** The item's detail page, or null when it has none (no uid, or an agent
 *  whose type is not known yet). */
function detailPage(item: AttentionItem, agentType: string | undefined): string | null {
  const detail = PAGES[item.kind]?.detail;
  if (!item.uid || !detail) return null;
  return detail({ uid: item.uid, title: item.title, agentType });
}

/** The page an item's name opens: its detail page, its kind's list, or
 *  Activity. `agentType` is the type of the agent an agent item is about. */
export function itemPage(item: AttentionItem, agentType?: string): string {
  const page = PAGES[item.kind];
  if (!page) return "/activity";
  return detailPage(item, agentType) ?? page.list;
}

/** The reasons the reconciler's memory-hook target reports about Coffer's hook
 *  in an agent's own settings: changed by hand (and not rewritten), missing,
 *  not trusted or switched off in the agent, or a settings file that does not
 *  parse. Each is dealt with on the agent's Hooks tab, whose hook row carries
 *  Repair. */
const HOOK_REASONS = new Set([
  "stale_command",
  "hook_missing",
  "hook_untrusted",
  "hook_disabled",
  "hook_trust_unknown",
  "unreadable_config",
]);

/** Whether an item is about Coffer's memory hook in one agent. */
function isHookItem(item: AttentionItem): boolean {
  return item.kind === "agent" && HOOK_REASONS.has(item.reason_code);
}

/** The page an item's one action opens — a missing secret is added on
 *  Secrets, a memory-hook problem is dealt with on the agent's Hooks tab. */
export function actionPage(item: AttentionItem, agentType?: string): string {
  if (item.reason_code === "mcp_missing_secret" || item.reason_code === "skill_missing_secret") {
    return "/secrets";
  }
  const detail = detailPage(item, agentType);
  if (isHookItem(item) && detail) return `${detail}/hooks`;
  return itemPage(item, agentType);
}

const VERBS = new Set(["connect", "test", "set_secret", "check", "run", "review", "repair"]);

/** i18n key of the action button's label; an unknown verb reads "Open". */
export function actionLabelKey(verb: string): string {
  return `overview.actions.${VERBS.has(verb) ? verb : "open"}`;
}

/** One item's label key: a memory hook's repair reads "Repair hook" rather
 *  than "Repair drift"; everything else goes by its verb. */
export function itemActionLabelKey(item: AttentionItem): string {
  if (isHookItem(item) && item.action.verb === "repair") return "overview.actions.repairHook";
  return actionLabelKey(item.action.verb);
}
