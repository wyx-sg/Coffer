// frontend/src/pages/activity/ChangesTab.tsx
//
// The Changes tab: the vault's audit log — who changed what, when — as a
// plain-language stream through the shared DataTable. Its own table, its own
// columns: an audit row has an actor, which neither of the other two records
// has, and it has no duration, status or level to pretend to.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/DataTable";
import { RawLog } from "@/components/RawLog";
import { useAudit } from "@/lib/hooks/useAudit";
import { translateApiError } from "@/lib/api/errors";
import { resolveTimeWindow } from "@/lib/timeRange";
import { formatDateTime } from "@/lib/utils";
import { ActivityFilters, type ActivityFilterState } from "./ActivityFilters";
import { auditSearchHaystack, describeActivity } from "./activityText";
import type { components } from "@/lib/api/types";

type AuditEntry = components["schemas"]["AuditEntryOut"];

/** The daemon caps an audit query at 500 rows. */
const LIMIT = 500;

/**
 * Actor options shown in the filter (besides "all"). Covers both the
 * request-origin actors derived from the `X-Coffer-Actor` header (`ui`/`cli`/
 * `api`) and the domain actors the backend records directly on audit rows
 * (`user`/`agent`/`channel` — see `audit_service.record(actor=…)`), plus the
 * daemon's own `system`. Each value has an `audit.actor.<value>` label.
 */
const ACTORS = ["ui", "cli", "api", "system", "user", "agent", "channel"] as const;

interface ChangesFiltersState extends ActivityFilterState {
  /** "all" or one of ACTORS — applied client-side. */
  actor: string;
}

const DEFAULT_FILTERS: ChangesFiltersState = {
  search: "",
  timeRange: "all",
  from: "",
  to: "",
  actor: "all",
};

interface Props {
  /** False while another tab is in front: no request, no discarded response. */
  enabled: boolean;
}

export function ChangesTab({ enabled }: Props) {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<ChangesFiltersState>(DEFAULT_FILTERS);

  // Memoise the window: resolveTimeWindow uses Date.now() for rolling presets,
  // so computing it inline would mint a fresh `since` every render — and
  // `since` is in the useAudit queryKey, so that would refetch /audit on every
  // keystroke. Recompute only when the time filter changes.
  const { timeRange, from, to } = filters;
  const { since, until } = useMemo(
    () => resolveTimeWindow({ timeRange, from, to }),
    [timeRange, from, to],
  );

  const { data, isLoading, error } = useAudit({ since, limit: LIMIT, enabled });

  // The daemon applies `since` server-side and returns the rows newest-first;
  // the custom-range upper bound, the actor and the free-text search run
  // client-side over at most 500 rows. No re-sort — DataTable preserves the
  // order it is handed.
  const entries = data?.entries;
  const { search, actor } = filters;
  const rows = useMemo(() => {
    let filtered = entries ?? [];
    if (until) filtered = filtered.filter((e) => e.timestamp <= until);
    if (actor !== "all") filtered = filtered.filter((e) => e.actor === actor);
    const query = search.trim().toLowerCase();
    if (query) filtered = filtered.filter((e) => auditSearchHaystack(t, e).includes(query));
    return filtered;
  }, [entries, until, actor, search, t]);

  const columns: Column<AuditEntry>[] = [
    {
      key: "time",
      header: t("activity.changes.table.time"),
      className: "w-44 whitespace-nowrap text-xs text-muted-foreground",
      cell: (e) => formatDateTime(e.timestamp),
    },
    {
      key: "activity",
      header: t("activity.changes.table.activity"),
      className: "text-sm break-words",
      cell: (e) => describeActivity(t, e),
    },
    {
      key: "actor",
      header: t("activity.changes.table.actor"),
      className: "w-28 text-xs text-muted-foreground",
      cell: (e) => t(`audit.actor.${e.actor}`, { defaultValue: e.actor }),
    },
  ];

  return (
    <div className="space-y-4">
      <ActivityFilters
        state={filters}
        onChange={setFilters}
        searchPlaceholder={t("audit.filter.searchPlaceholder")}
      >
        <Select value={filters.actor} onValueChange={(v) => setFilters({ ...filters, actor: v })}>
          <SelectTrigger aria-label={t("audit.filter.actor")} className="h-9 w-auto min-w-[8rem]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("audit.filter.all")}</SelectItem>
            {ACTORS.map((a) => (
              <SelectItem key={a} value={a}>
                {t(`audit.actor.${a}`, { defaultValue: a })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </ActivityFilters>

      {/* isLoading, not isPending: a disabled query stays "pending" forever,
          which would leave a tab that has never been opened stuck on skeleton
          rows the moment it is. An error renders here, inside this tab — a
          failing /audit must not blank the other two records. */}
      {error ? (
        <Card className="paper-card border-destructive/40">
          <CardContent className="py-4 text-destructive">{translateApiError(t, error)}</CardContent>
        </Card>
      ) : (
        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(e) => String(e.id)}
          isLoading={isLoading}
          getRowDetail={(e) => (
            <div className="px-4 py-3">
              <RawLog record={e} />
            </div>
          )}
          emptyMessage={t("activity.changes.emptyState")}
        />
      )}
    </div>
  );
}
