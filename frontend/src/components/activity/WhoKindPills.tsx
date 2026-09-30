// src/components/activity/WhoKindPills.tsx — Activity's two multi-select filters: who made a record, and what kind it is.
//
// Design 6.1.03 and 6.1.04: each lists its values with how many loaded
// records carry them. Agent lists the agents, then who else makes changes
// (you, the command line, Coffer, sync); Kind lists MCP calls, Changes with
// each kind of change under it, and daemon records. Ticking Changes ticks
// every kind under it; unticking one keeps the rest.
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import {
  CHANGE_CATEGORIES,
  WHO_ACTORS,
  recordKind,
  recordWho,
  tally,
  type ActivityFilters,
} from "@/lib/activity/filters";
import type { ActivityRecord, ActivityTab } from "@/lib/activity/records";
import type { TabCount } from "@/lib/hooks/useActivityFeed";
import { ChecklistPill, type CheckGroup, type CheckItem } from "./ChecklistPill";

interface Props {
  tab: ActivityTab;
  filters: ActivityFilters;
  set: (patch: Partial<ActivityFilters>) => void;
  /** The loaded records before the client-side filters, for the counts. */
  loaded: readonly ActivityRecord[];
}

function toggle(values: readonly string[], value: string): string[] {
  return values.includes(value) ? values.filter((v) => v !== value) : [...values, value];
}

/** The kind values in the order the pill names them: calls, changes, each kind, daemon. */
function kindOrder(value: string): number {
  if (value === "calls") return 0;
  if (value === "changes") return 1;
  if (value === "daemon") return 99;
  return 2 + CHANGE_CATEGORIES.indexOf(value.slice("change:".length) as never);
}

function kindWords(t: TFunction, value: string, first: boolean): string {
  if (value.startsWith("change:")) {
    return t(`activity.filters.changeKinds.${value.slice("change:".length)}`);
  }
  return t(`activity.filters.${first ? "kindPill" : "kindInline"}.${value}`);
}

/** "Calls, changes" — or "4 kinds" once the list would not fit a pill. */
function kindLabel(t: TFunction, kinds: readonly string[]): string | null {
  if (kinds.length === 0) return null;
  if (kinds.length > 3) return t("activity.filters.kindCount", { count: kinds.length });
  return [...kinds]
    .sort((a, b) => kindOrder(a) - kindOrder(b))
    .map((k, i) => kindWords(t, k, i === 0))
    .join(", ");
}

/** @ui-only An agent as the who filter lists it. */
interface AgentOption {
  uid: string;
  type: string;
  name: string;
}

export function WhoPill({
  tab,
  filters,
  set,
  loaded,
  agents,
  agentNames,
}: Props & { agents: AgentOption[]; agentNames: ReadonlyMap<string, string> }) {
  const { t } = useTranslation();
  const whoCounts = tally(loaded, (r) => recordWho(r, agentNames));
  const byShown = tab === "mcp" ? filters.by.filter((b) => b.startsWith("agent:")) : filters.by;
  const agentItems: CheckItem[] = agents.map((a) => ({
    value: `agent:${a.uid}`,
    text: a.name,
    label: (
      <span className="inline-flex items-center gap-2">
        <AgentBadge type={a.type} name={a.name} size="sm" tooltip={false} />
        {a.name}
      </span>
    ),
    count: whoCounts.get(`agent:${a.uid}`) ?? 0,
    checked: filters.by.includes(`agent:${a.uid}`),
  }));
  // The four who-groups are always offered; another (the API, a channel) only
  // once a loaded change carries it.
  const actorGroups = [
    ...WHO_ACTORS,
    ...[...whoCounts.keys()]
      .filter((k) => k.startsWith("actor:"))
      .map((k) => k.slice("actor:".length))
      .filter((g) => !(WHO_ACTORS as readonly string[]).includes(g)),
  ];
  const actorItems: CheckItem[] = actorGroups.map((group) => ({
    value: `actor:${group}`,
    text: t(`activity.actor.${group}`, { defaultValue: group }),
    label: t(`activity.actor.${group}`, { defaultValue: group }),
    count: whoCounts.get(`actor:${group}`) ?? 0,
    checked: filters.by.includes(`actor:${group}`),
  }));
  const whoGroups: CheckGroup[] =
    tab === "mcp"
      ? [{ items: agentItems }]
      : [{ items: agentItems }, { label: t("activity.filters.notAnAgent"), items: actorItems }];
  const whoLabel = byShown.length
    ? [...agentItems, ...actorItems]
        .filter((i) => byShown.includes(i.value))
        .map((i) => i.text)
        .join(", ")
    : null;
  return (
    <ChecklistPill
      label={t("activity.filters.by")}
      valueLabel={whoLabel}
      groups={whoGroups}
      onToggle={(value) => set({ by: toggle(filters.by, value) })}
      onClear={() => set({ by: [] })}
      summary={byShown.length ? t("activity.filters.selected", { count: byShown.length }) : null}
      searchPlaceholder={t("activity.filters.findAgent")}
    />
  );
}

export function KindPill({
  tab,
  filters,
  set,
  loaded,
  counts,
}: Props & { counts: Record<ActivityTab, TabCount> }) {
  const { t } = useTranslation();
  const kindCounts = tally(loaded, recordKind);
  const allChanges = filters.kinds.includes("changes");
  const categories = CHANGE_CATEGORIES.filter(
    (c) => kindCounts.has(`change:${c}`) || filters.kinds.includes(`change:${c}`),
  );
  const categoryItems = (indent: boolean): CheckItem[] =>
    categories.map((c) => ({
      value: `change:${c}`,
      text: t(`activity.filters.changeKinds.${c}`),
      label: t(`activity.filters.changeKinds.${c}`),
      count: kindCounts.get(`change:${c}`) ?? 0,
      checked: allChanges || filters.kinds.includes(`change:${c}`),
      indent,
    }));
  const someChanges = filters.kinds.some((k) => k.startsWith("change:"));
  const kindItems: CheckItem[] =
    tab === "everything"
      ? [
          {
            value: "calls",
            text: t("activity.filters.kinds.calls"),
            label: t("activity.filters.kinds.calls"),
            count: counts.mcp.value,
            checked: filters.kinds.includes("calls"),
            strong: true,
          },
          {
            value: "changes",
            text: t("activity.filters.kinds.changes"),
            label: t("activity.filters.kinds.changes"),
            count: counts.changes.value,
            checked: allChanges ? true : someChanges ? "mixed" : false,
            strong: true,
          },
          ...categoryItems(true),
          {
            value: "daemon",
            text: t("activity.filters.kinds.daemon"),
            label: t("activity.filters.kinds.daemon"),
            count: counts.daemon.value,
            checked: filters.kinds.includes("daemon"),
            strong: true,
          },
        ]
      : categoryItems(false);

  const toggleKind = (value: string) => {
    const kinds = filters.kinds;
    const withoutChanges = kinds.filter((k) => k !== "changes" && !k.startsWith("change:"));
    if (value === "changes") {
      set({ kinds: allChanges || someChanges ? withoutChanges : [...withoutChanges, "changes"] });
      return;
    }
    if (value.startsWith("change:") && allChanges) {
      // Unticking one kind under a ticked Changes keeps every other kind.
      const rest = categories.map((c) => `change:${c}`).filter((k) => k !== value);
      set({ kinds: [...withoutChanges, ...rest] });
      return;
    }
    const next = toggle(kinds, value);
    const chosen = next.filter((k) => k.startsWith("change:"));
    // Every kind ticked one by one is Changes as a whole (Everything only).
    if (tab === "everything" && categories.length > 0 && chosen.length === categories.length) {
      set({ kinds: [...next.filter((k) => !k.startsWith("change:")), "changes"] });
      return;
    }
    set({ kinds: next });
  };

  const kindsShown =
    tab === "everything" ? filters.kinds : filters.kinds.filter((k) => k.startsWith("change:"));
  const everythingButDaemon =
    kindsShown.length === 2 && kindsShown.includes("calls") && kindsShown.includes("changes");
  const kindSummary = kindsShown.length
    ? everythingButDaemon
      ? t("activity.filters.kinds.notDaemon")
      : t("activity.filters.selected", { count: kindsShown.length })
    : null;

  return (
    <ChecklistPill
      label={t("activity.filters.kind")}
      valueLabel={kindLabel(t, kindsShown)}
      groups={[{ items: kindItems }]}
      onToggle={toggleKind}
      onClear={() => set({ kinds: [] })}
      summary={kindSummary}
    />
  );
}
