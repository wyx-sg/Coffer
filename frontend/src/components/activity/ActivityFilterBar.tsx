// src/components/activity/ActivityFilterBar.tsx — the filter row of the visible Activity tab (Foundations 0.2.06).
//
// Position never changes, only which controls a tab affords (design 6.2.04–10):
// Everything — search, time range, By, Kind (Tool calls / Changes / Daemon
// records); Changes — search, time range, By, Kind (the eleven kinds of
// change); Tool calls — status segmented (All / OK / Failed), search, time
// range, By (agents only); Daemon log — level segmented (All / Info /
// Warnings / Errors), search, time range, Logger. There is no server filter:
// the search matches a server's name. "Clear filters" sits at the far right
// while anything is set; the counts are gone from every pill.
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { FilterPill, FilterRow, TimeRangePill, type FilterOption } from "@/components/filters";
import { Segmented } from "@/components/ui/segmented";
import {
  CHANGE_CATEGORIES,
  RECORD_KINDS,
  WHO_ACTORS,
  filtersNarrow,
  type ActivityFilters,
  type StatusFilter,
} from "@/lib/activity/filters";
import type { ActivityTab } from "@/lib/activity/records";
import { RANGE_PRESETS } from "@/lib/hooks/useActivityView";

/** @ui-only An agent as the By filter lists it. */
interface ByAgent {
  uid: string;
  type: string;
  name: string;
}

interface Props {
  tab: ActivityTab;
  filters: ActivityFilters;
  onChange: (next: ActivityFilters) => void;
  onClear: () => void;
  agents: ByAgent[];
  /** Loggers seen in the loaded daemon records. */
  loggers: string[];
}

const STATUSES: readonly StatusFilter[] = ["all", "ok", "failed"];
const LEVELS = ["", "info", "warning", "error"] as const;

/** The By pill's long list searches above this many values (FilterPill's own threshold). */
const FEW = 8;

export function ActivityFilterBar({ tab, filters, onChange, onClear, agents, loggers }: Props) {
  const { t } = useTranslation();
  const set = (patch: Partial<ActivityFilters>) => onChange({ ...filters, ...patch });

  const presets = RANGE_PRESETS.map((id) => ({ id, label: t(`activity.time.${id}`) }));
  const time = (
    <TimeRangePill
      key="time"
      value={filters.range}
      onChange={(range) => set({ range })}
      presets={presets}
    />
  );

  const agentOptions: FilterOption[] = agents.map((a) => ({
    value: `agent:${a.uid}`,
    label: a.name,
    icon: <AgentBadge type={a.type} name={a.name} size="sm" tooltip={false} />,
    group: "agents",
  }));
  const actorOptions: FilterOption[] = WHO_ACTORS.map((actor) => ({
    value: `actor:${actor}`,
    label: t(`activity.actor.${actor}`),
    group: "actors",
  }));
  const byOptions = tab === "mcp" ? agentOptions : [...agentOptions, ...actorOptions];
  const by = (
    <FilterPill
      key="by"
      label={t("activity.filters.by")}
      options={byOptions}
      groups={
        tab === "mcp"
          ? undefined
          : [
              { id: "agents", label: t("activity.filters.agents") },
              { id: "actors", label: t("activity.filters.notAnAgent"), last: true },
            ]
      }
      searchPlaceholder={t("activity.filters.findAgent")}
      fixedOrder={byOptions.length <= FEW}
      value={filters.by}
      onChange={(next) => set({ by: next })}
    />
  );

  const kindOptions: FilterOption[] =
    tab === "changes"
      ? CHANGE_CATEGORIES.map((c) => ({ value: c, label: t(`activity.filters.changeKinds.${c}`) }))
      : RECORD_KINDS.map((k) => ({ value: k, label: t(`activity.filters.kinds.${k}`) }));
  const kind = (
    <FilterPill
      key="kind"
      label={t("activity.filters.kind")}
      options={kindOptions}
      searchPlaceholder={t("activity.filters.findKind")}
      fixedOrder
      value={filters.kinds}
      onChange={(next) => set({ kinds: next })}
    />
  );

  let segmented;
  let pills;
  if (tab === "mcp") {
    segmented = (
      <Segmented
        label={t("activity.filters.statusLabel")}
        value={filters.status}
        options={STATUSES.map((s) => ({
          value: s,
          label: t(`activity.filters.statusOption.${s}`),
        }))}
        onChange={(status) => set({ status })}
      />
    );
    pills = [time, by];
  } else if (tab === "daemon") {
    segmented = (
      <Segmented
        label={t("activity.filters.levelLabel")}
        value={filters.level}
        options={LEVELS.map((level) => ({
          value: level,
          label: t(`activity.filters.level.${level || "all"}`),
        }))}
        onChange={(level) => set({ level })}
      />
    );
    pills = [
      time,
      <FilterPill
        key="logger"
        mode="single"
        label={t("activity.filters.logger")}
        options={loggers.map((logger) => ({ value: logger, label: logger }))}
        searchPlaceholder={t("activity.filters.findLogger")}
        value={filters.logger}
        onChange={(logger) => set({ logger })}
      />,
    ];
  } else {
    pills = [time, by, kind];
  }

  return (
    <FilterRow
      segmented={segmented}
      search={{
        value: filters.search,
        onChange: (search) => set({ search }),
        placeholder: t(`activity.filters.search.${tab}`),
        shortcut: "/",
      }}
      active={filtersNarrow(filters, tab)}
      onClear={onClear}
    >
      {pills}
    </FilterRow>
  );
}
