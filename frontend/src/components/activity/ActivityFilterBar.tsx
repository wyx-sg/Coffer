// src/components/activity/ActivityFilterBar.tsx — the filters of the visible Activity tab, as pills plus a free-text box.
//
// Every tab filters by time range and free text; each adds the filters its
// records afford (spec web-ui "Filter each Activity tab and expand any row"):
// Everything an agent (or who else), a server and a kind; Changes who and
// the kind of change; MCP calls an agent, a server and a status; the Daemon
// log a severity floor and a logger. Agent and Kind choose several values at
// once, each with its count (design 6.1.03, 6.1.04). "/" focuses the text box
// from anywhere on the page.
import { useEffect, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { type ActivityRecord, type ActivityTab } from "@/lib/activity/records";
import type { ActivityFilters } from "@/lib/activity/filters";
import type { TabCount } from "@/lib/hooks/useActivityFeed";
import { cn } from "@/lib/utils";
import { ActivityTimeRange } from "./ActivityTimeRange";
import { FilterPill } from "./FilterPill";
import { KindPill, WhoPill } from "./WhoKindPills";

const CALL_STATUSES = ["ok", "error", "timeout", "denied"] as const;

/** The daemon tab's severity floors, least to most severe. */
const LEVELS = ["", "info", "warning", "error"] as const;

/** @ui-only An agent as the who filter lists it. */
interface AgentOption {
  uid: string;
  type: string;
  name: string;
}

/** @ui-only An MCP server as the server filter lists it. */
interface ServerOption {
  uid: string;
  label: string;
}

interface Props {
  tab: ActivityTab;
  filters: ActivityFilters;
  onChange: (next: ActivityFilters) => void;
  agents: AgentOption[];
  agentNames: ReadonlyMap<string, string>;
  servers: ServerOption[];
  /** Loggers seen in the loaded daemon records. */
  loggers: string[];
  /** The loaded records before the client-side filters, for the pills' counts. */
  loaded: readonly ActivityRecord[];
  counts: Record<ActivityTab, TabCount>;
  /** Shown after the text box (the daemon log's "Open log file"). */
  trailing?: ReactNode;
}

export function ActivityFilterBar({
  tab,
  filters,
  onChange,
  agents,
  agentNames,
  servers,
  loggers,
  loaded,
  counts,
  trailing,
}: Props) {
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

  const timePill = (
    <ActivityTimeRange
      timeRange={filters.timeRange}
      from={filters.from}
      to={filters.to}
      onChange={(v) => set(v)}
    />
  );

  return (
    <div className="flex flex-wrap items-center gap-2">
      {tab === "daemon" ? (
        <>
          <div
            role="radiogroup"
            aria-label={t("activity.filters.levelLabel")}
            className="inline-flex items-center gap-0.5 rounded-md border border-border-subtle bg-surface-sunken p-[3px]"
          >
            {LEVELS.map((level) => (
              <button
                key={level || "all"}
                type="button"
                role="radio"
                aria-checked={filters.level === level}
                onClick={() => set({ level })}
                className={cn(
                  "h-6 rounded-sm px-2.5 text-xs font-label text-text-muted transition-colors duration-fast hover:text-text",
                  filters.level === level &&
                    "bg-surface-raised text-text shadow-sm ring-1 ring-border",
                )}
              >
                {t(`activity.filters.level.${level || "all"}`)}
              </button>
            ))}
          </div>
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
          {timePill}
        </>
      ) : (
        <>
          {timePill}
          <WhoPill
            tab={tab}
            filters={filters}
            set={set}
            loaded={loaded}
            agents={agents}
            agentNames={agentNames}
          />
        </>
      )}
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
        <KindPill tab={tab} filters={filters} set={set} loaded={loaded} counts={counts} />
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
      <div className="ml-auto flex w-full items-center gap-2 sm:w-auto">
        <div
          ref={searchBox}
          className={cn("relative w-full", tab === "daemon" ? "sm:w-56" : "sm:w-64")}
        >
          <SearchInput
            value={filters.search}
            onChange={(search) => set({ search })}
            placeholder={t(`activity.filters.search.${tab}`)}
            ariaLabel={t("activity.filters.searchLabel")}
          />
          {filters.search || tab === "daemon" ? null : (
            <kbd
              aria-hidden
              className="pointer-events-none absolute right-2.5 top-1/2 inline-flex h-[18px] -translate-y-1/2 items-center rounded-[4px] border border-border bg-surface-raised px-[5px] font-sans text-2xs text-text-subtle"
            >
              /
            </kbd>
          )}
        </div>
        {trailing}
      </div>
    </div>
  );
}
