// src/pages/activity/ActivityFilterBar.tsx — the filters of the visible Activity tab, as pills plus a free-text box.
//
// Every tab filters by time range and free text; each adds the filters its
// records afford (spec web-ui "Filter each Activity tab and expand any row"):
// Everything and Changes a who and a kind, Everything and MCP calls a server,
// MCP calls a status, the Daemon log a severity floor and a logger. "/"
// focuses the text box from anywhere on the page.
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { SearchInput } from "@/components/SearchInput";
import { TimeRangePicker } from "@/components/TimeRangePicker";
import { CHANGE_KINDS, type ActivityFilters, type ActivityTab } from "@/lib/activity/records";
import { cn } from "@/lib/utils";
import { FilterPill, type PillGroup } from "./FilterPill";

/** The audit actors that are not an agent. */
const NON_AGENT_ACTORS = ["ui", "cli", "api", "system", "channel"] as const;

const CALL_STATUSES = ["ok", "error", "timeout", "denied"] as const;

/** The daemon tab's severity floors, least to most severe. */
const LEVELS = ["", "info", "warning", "error"] as const;

/** @ui-only An agent as the who filter lists it. */
export interface AgentOption {
  uid: string;
  type: string;
  name: string;
}

/** @ui-only An MCP server as the server filter lists it. */
export interface ServerOption {
  uid: string;
  label: string;
}

interface Props {
  tab: ActivityTab;
  filters: ActivityFilters;
  onChange: (next: ActivityFilters) => void;
  agents: AgentOption[];
  servers: ServerOption[];
  /** Loggers seen in the loaded daemon records. */
  loggers: string[];
}

export function ActivityFilterBar({ tab, filters, onChange, agents, servers, loggers }: Props) {
  const { t } = useTranslation();
  const searchBox = useRef<HTMLDivElement>(null);
  const set = (patch: Partial<ActivityFilters>) => onChange({ ...filters, ...patch });

  // "/" jumps to the text box, as the key hint beside it says.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))
      ) {
        return;
      }
      const input = searchBox.current?.querySelector("input");
      if (!input) return;
      event.preventDefault();
      input.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const agentGroup: PillGroup = {
    label: tab === "mcp" ? undefined : t("activity.filters.agents"),
    options: agents.map((a) => ({
      value: `agent:${a.uid}`,
      label: (
        <span className="inline-flex items-center gap-2">
          <AgentBadge type={a.type} name={a.name} size="sm" tooltip={false} />
          {a.name}
        </span>
      ),
    })),
  };
  const actorGroup: PillGroup = {
    label: t("activity.filters.notAnAgent"),
    options: NON_AGENT_ACTORS.map((actor) => ({
      value: `actor:${actor}`,
      label: t(`activity.actor.${actor}`),
    })),
  };
  const byGroups = tab === "mcp" ? [agentGroup] : [agentGroup, actorGroup];

  const changeKindGroup: PillGroup = {
    label: tab === "everything" ? t("activity.filters.kinds.changes") : undefined,
    options: [
      ...(tab === "everything"
        ? [{ value: "changes", label: t("activity.filters.kinds.allChanges") }]
        : []),
      ...CHANGE_KINDS.map((kind) => ({
        value: `change:${kind}`,
        label: t(`activity.filters.changeKinds.${kind}`),
      })),
    ],
  };
  const kindGroups: PillGroup[] =
    tab === "everything"
      ? [
          { options: [{ value: "calls", label: t("activity.filters.kinds.calls") }] },
          changeKindGroup,
          {
            options: [
              { value: "daemon", label: t("activity.filters.kinds.daemon") },
              { value: "not-daemon", label: t("activity.filters.kinds.notDaemon") },
            ],
          },
        ]
      : [changeKindGroup];

  return (
    <div className="flex flex-wrap items-center gap-2">
      <TimeRangePicker
        timeRange={filters.timeRange}
        from={filters.from}
        to={filters.to}
        onChange={(v) => set(v)}
      />
      {tab === "daemon" ? (
        <div
          role="radiogroup"
          aria-label={t("activity.filters.levelLabel")}
          className="inline-flex h-control-sm items-center rounded-md border border-border bg-surface-sunken p-0.5"
        >
          {LEVELS.map((level) => (
            <button
              key={level || "all"}
              type="button"
              role="radio"
              aria-checked={filters.level === level}
              onClick={() => set({ level })}
              className={cn(
                "h-full rounded-sm px-2 text-xs text-text-muted transition-colors duration-fast hover:text-text",
                filters.level === level && "bg-surface-raised font-label text-text shadow-sm",
              )}
            >
              {t(`activity.filters.level.${level || "all"}`)}
            </button>
          ))}
        </div>
      ) : null}
      {tab !== "daemon" ? (
        <FilterPill
          label={t("activity.filters.by")}
          value={filters.by}
          anyValue="any"
          groups={byGroups}
          onChange={(by) => set({ by })}
        />
      ) : null}
      {tab === "everything" || tab === "mcp" ? (
        <FilterPill
          label={t("activity.filters.server")}
          value={filters.server}
          anyValue="any"
          groups={[{ options: servers.map((s) => ({ value: s.uid, label: s.label })) }]}
          onChange={(server) => set({ server })}
        />
      ) : null}
      {tab === "everything" || tab === "changes" ? (
        <FilterPill
          label={t("activity.filters.kind")}
          value={filters.kind}
          anyValue="any"
          groups={kindGroups}
          onChange={(kind) => set({ kind })}
        />
      ) : null}
      {tab === "mcp" ? (
        <FilterPill
          label={t("activity.filters.status")}
          value={filters.status}
          anyValue="any"
          groups={[
            {
              options: CALL_STATUSES.map((s) => ({
                value: s,
                label: t(`activity.status.${s}`),
              })),
            },
          ]}
          onChange={(status) => set({ status })}
        />
      ) : null}
      {tab === "daemon" ? (
        <FilterPill
          label={t("activity.filters.logger")}
          value={filters.logger}
          anyValue="any"
          groups={[
            {
              options: loggers.map((logger) => ({
                value: logger,
                label: <span className="font-mono text-xs">{logger}</span>,
              })),
            },
          ]}
          onChange={(logger) => set({ logger })}
        />
      ) : null}
      <div ref={searchBox} className="ml-auto w-full sm:w-64">
        <SearchInput
          value={filters.search}
          onChange={(search) => set({ search })}
          placeholder={t(`activity.filters.search.${tab}`)}
          ariaLabel={t("activity.filters.searchLabel")}
        />
      </div>
    </div>
  );
}
