import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Card, CardContent } from "@/components/ui/card";
import { useAudit } from "@/lib/hooks/useAudit";
import { translateApiError } from "@/lib/api/errors";
import { AuditFilters, type AuditFiltersState } from "@/pages/audit/AuditFilters";
import { AuditTable } from "@/pages/audit/AuditTable";
import { auditSearchHaystack } from "@/pages/audit/auditText";
import { Pagination } from "@/components/Pagination";

const RANGE_MS: Record<string, number> = {
  "1h": 3_600_000,
  "6h": 21_600_000,
  "24h": 86_400_000,
  "7d": 604_800_000,
  "30d": 2_592_000_000,
};

/** A typed datetime ("YYYY-MM-DD HH:mm:ss") -> ISO; "" or invalid -> undefined. */
function parseDateTime(value: string): string | undefined {
  const v = value.trim();
  if (!v) return undefined;
  const d = new Date(v.replace(" ", "T"));
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString();
}

/** Resolve the active time filter into a [since, until] window. */
function resolveWindow(f: AuditFiltersState): {
  since?: string;
  until?: string;
} {
  if (f.timeRange === "custom") {
    return { since: parseDateTime(f.from), until: parseDateTime(f.to) };
  }
  const ms = RANGE_MS[f.timeRange];
  return { since: ms ? new Date(Date.now() - ms).toISOString() : undefined };
}

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

  const { since, until } = resolveWindow(filters);
  const { data, isPending, error } = useAudit({ since, limit: 500 });

  let filtered = data?.entries ?? [];
  if (until) filtered = filtered.filter((e) => e.timestamp <= until);
  if (filters.actor !== "all") {
    filtered = filtered.filter((e) => e.actor === filters.actor);
  }
  const query = filters.search.trim().toLowerCase();
  if (query) {
    filtered = filtered.filter((e) => auditSearchHaystack(t, e).includes(query));
  }

  const sorted = [...filtered].sort((a, b) => {
    const cmp = a.timestamp < b.timestamp ? -1 : a.timestamp > b.timestamp ? 1 : 0;
    return sortDir === "asc" ? cmp : -cmp;
  });

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
