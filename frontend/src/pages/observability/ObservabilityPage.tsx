import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Card, CardContent } from "@/components/ui/card";
import { useAudit } from "@/lib/hooks/useAudit";
import { translateApiError } from "@/lib/api/errors";
import { resolveTimeWindow } from "@/lib/timeRange";
import { AuditFilters, type AuditFiltersState } from "@/pages/audit/AuditFilters";
import { AuditTable } from "@/pages/audit/AuditTable";
import { auditSearchHaystack } from "@/pages/audit/auditText";
import { Pagination } from "@/components/Pagination";

/**
 * Observability — the audit log as a plain-language activity stream.
 * The time range is applied server-side via `since`; the daemon caps a
 * query at 500 rows, so the custom-range upper bound, free-text search,
 * actor filter, and paging run client-side — ample for a local
 * single-user audit log.
 */
export function ObservabilityPage() {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<AuditFiltersState>({
    search: "",
    timeRange: "all",
    actor: "all",
    from: "",
    to: "",
  });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  // Memoise the window: resolveTimeWindow uses Date.now() for rolling
  // presets, so computing it inline would mint a fresh `since` every render
  // — and `since` is in the useAudit queryKey, so that would refetch /audit
  // on every keystroke/sort/poll. Recompute only when the time filter changes.
  const { timeRange, from, to } = filters;
  const { since, until } = useMemo(
    () => resolveTimeWindow({ timeRange, from, to }),
    [timeRange, from, to],
  );
  const { data, isPending, error } = useAudit({ since, limit: 500 });

  // Filter + sort run client-side over <=500 rows; memoise so unrelated
  // re-renders (e.g. paging, sort toggle) don't re-scan and re-allocate,
  // and the per-row i18n haystack only recomputes when inputs change.
  const entries = data?.entries;
  const sorted = useMemo(() => {
    let filtered = entries ?? [];
    if (until) filtered = filtered.filter((e) => e.timestamp <= until);
    if (filters.actor !== "all") {
      filtered = filtered.filter((e) => e.actor === filters.actor);
    }
    const query = filters.search.trim().toLowerCase();
    if (query) {
      filtered = filtered.filter((e) => auditSearchHaystack(t, e).includes(query));
    }
    return [...filtered].sort((a, b) => {
      const cmp = a.timestamp < b.timestamp ? -1 : a.timestamp > b.timestamp ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [entries, until, filters.actor, filters.search, sortDir, t]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, pageCount);
  const pageEntries = sorted.slice((safePage - 1) * pageSize, safePage * pageSize);

  const applyFilters = (next: AuditFiltersState) => {
    setFilters(next);
    setPage(1);
  };

  const toggleSort = () => {
    setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-3xl tracking-tight">{t("observability.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("observability.subtitle")}</p>
      </header>

      <Card className="paper-card">
        <CardContent className="py-4">
          <AuditFilters state={filters} onChange={applyFilters} />
        </CardContent>
      </Card>

      {isPending ? (
        <Card className="paper-card">
          <CardContent className="py-10 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      ) : error ? (
        <Card className="paper-card border-destructive/40">
          <CardContent className="py-4 text-destructive">{translateApiError(t, error)}</CardContent>
        </Card>
      ) : (
        <>
          <AuditTable entries={pageEntries} sortDir={sortDir} onToggleSort={toggleSort} />
          <Pagination
            page={safePage}
            pageCount={pageCount}
            total={sorted.length}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={(s) => {
              setPageSize(s);
              setPage(1);
            }}
          />
        </>
      )}
    </div>
  );
}
