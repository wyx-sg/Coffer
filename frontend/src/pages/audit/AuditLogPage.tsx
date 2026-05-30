import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ScrollText } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/DataTable";
import { RawLog } from "@/components/RawLog";
import { useAudit } from "@/lib/hooks/useAudit";
import { translateApiError } from "@/lib/api/errors";
import { resolveTimeWindow } from "@/lib/timeRange";
import { formatDateTime } from "@/lib/utils";
import { AuditFilters, type AuditFiltersState } from "@/pages/audit/AuditFilters";
import { auditSearchHaystack, describeActivity } from "@/pages/audit/auditText";
import type { components } from "@/lib/api/types";

type AuditEntry = components["schemas"]["AuditEntryOut"];

/**
 * Audit log — the activity trail (who did what, when) as a plain-language
 * stream rendered through the shared DataTable (unified with the Agents and
 * MCP-servers surfaces). The time range is applied server-side via `since`;
 * the daemon caps a query at 500 rows, so the custom-range upper bound,
 * free-text search, and actor filter run client-side — ample for a local
 * single-user audit log. Rows are shown newest-first; DataTable owns the
 * search box's sibling-free expand chevron, the row detail (raw JSON), and
 * pagination.
 *
 * Note: this is the Audit log, distinct from a future "Observability"
 * (system health / metrics) surface (see ADR-007 §System).
 */
export function AuditLogPage() {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<AuditFiltersState>({
    search: "",
    timeRange: "all",
    actor: "all",
    from: "",
    to: "",
  });

  // Memoise the window: resolveTimeWindow uses Date.now() for rolling
  // presets, so computing it inline would mint a fresh `since` every render
  // — and `since` is in the useAudit queryKey, so that would refetch /audit
  // on every keystroke/poll. Recompute only when the time filter changes.
  const { timeRange, from, to } = filters;
  const { since, until } = useMemo(
    () => resolveTimeWindow({ timeRange, from, to }),
    [timeRange, from, to],
  );
  const { data, isPending, error } = useAudit({ since, limit: 500 });

  // Filter + sort run client-side over <=500 rows; memoise so unrelated
  // re-renders (e.g. DataTable paging) don't re-scan and re-allocate, and the
  // per-row i18n haystack only recomputes when inputs change. Rows are sorted
  // newest-first here; DataTable preserves the order it is handed.
  const entries = data?.entries;
  const rows = useMemo(() => {
    let filtered = entries ?? [];
    if (until) filtered = filtered.filter((e) => e.timestamp <= until);
    if (filters.actor !== "all") {
      filtered = filtered.filter((e) => e.actor === filters.actor);
    }
    const query = filters.search.trim().toLowerCase();
    if (query) {
      filtered = filtered.filter((e) => auditSearchHaystack(t, e).includes(query));
    }
    return [...filtered].sort((a, b) =>
      a.timestamp < b.timestamp ? 1 : a.timestamp > b.timestamp ? -1 : 0,
    );
  }, [entries, until, filters.actor, filters.search, t]);

  const columns: Column<AuditEntry>[] = [
    {
      key: "time",
      header: t("audit.table.time"),
      className: "w-44 whitespace-nowrap text-xs text-muted-foreground",
      cell: (e) => formatDateTime(e.timestamp),
    },
    {
      key: "activity",
      header: t("audit.table.activity"),
      className: "text-sm",
      cell: (e) => describeActivity(t, e),
    },
    {
      key: "actor",
      header: t("audit.table.actor"),
      className: "w-28 text-xs text-muted-foreground",
      cell: (e) => t(`audit.actor.${e.actor}`, { defaultValue: e.actor }),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader icon={ScrollText} title={t("audit.title")} subtitle={t("audit.subtitle")} />

      <div className="space-y-4">
        <AuditFilters state={filters} onChange={setFilters} />

        {isPending ? (
          <Card className="paper-card">
            <CardContent className="py-10 text-center text-muted-foreground">
              {t("common.loading")}
            </CardContent>
          </Card>
        ) : error ? (
          <Card className="paper-card border-destructive/40">
            <CardContent className="py-4 text-destructive">
              {translateApiError(t, error)}
            </CardContent>
          </Card>
        ) : (
          <DataTable
            rows={rows}
            columns={columns}
            rowKey={(e) => String(e.id)}
            getRowDetail={(e) => (
              <div className="px-4 py-3">
                <RawLog record={e} />
              </div>
            )}
            emptyMessage={t("audit.emptyState")}
          />
        )}
      </div>
    </div>
  );
}
