// frontend/src/kinds/mcp/InvocationsTable.tsx
//
// A server's MCP invocation log rendered through the shared DataTable (unified
// with the audit log and the other resource surfaces): the InvocationsFilters
// control bar drives the fetch (status + time window are query params), while
// free-text search narrows client-side. DataTable owns pagination and the
// per-row expand chevron whose detail is the invocation's raw JSON record.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/DataTable";
import { RawLog } from "@/components/RawLog";
import { useMcpInvocations } from "@/lib/hooks/useMcpInvocations";
import { translateApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/utils";
import { resolveTimeWindow } from "@/lib/timeRange";
import { invocationStatusClass } from "@/lib/statusColors";
import { InvocationsFilters, type InvocationsFiltersState } from "./InvocationsFilters";
import type { components } from "@/lib/api/types";

type InvocationOut = components["schemas"]["InvocationOut"];

interface Props {
  serverName: string;
}

const DEFAULT_FILTERS: InvocationsFiltersState = {
  search: "",
  timeRange: "all",
  from: "",
  to: "",
  status: "all",
};

// Stable per-row identity: the daemon returns no id, so pair the timestamp with
// the row's position in the *full fetched* list — assigned before client-side
// search/time filtering so narrowing the view doesn't reshuffle _id and
// collapse an expanded row (DataTable tracks expansion by this key).
type InvocationRow = InvocationOut & { _id: string };

/** Drop the synthetic _id so the raw log shows the daemon's record verbatim. */
function stripId({ _id, ...record }: InvocationRow): InvocationOut {
  void _id;
  return record;
}

export function InvocationsTable({ serverName }: Props) {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<InvocationsFiltersState>(DEFAULT_FILTERS);

  // Memoise the window so a rolling preset's Date.now()-based `since`
  // (which is part of the useMcpInvocations queryKey) is stable across
  // renders and doesn't refetch on every keystroke/poll. Recompute only
  // when the time filter changes.
  const { timeRange, from, to } = filters;
  const { since, until } = useMemo(
    () => resolveTimeWindow({ timeRange, from, to }),
    [timeRange, from, to],
  );

  const { data, isPending, error, refetch } = useMcpInvocations({
    serverName,
    status: filters.status === "all" ? undefined : filters.status,
    since,
  });

  const allRows = data?.invocations ?? [];

  // The daemon applies `since` server-side; the custom-range upper bound
  // (`until`) and the free-text search run client-side. Memoised so typing
  // in the search box doesn't re-scan every row on unrelated re-renders.
  // Hooks run before any early return.
  const q = filters.search.trim().toLowerCase();
  const invocations = data?.invocations;
  const rows = useMemo<InvocationRow[]>(() => {
    // Stamp _id from the position in the full fetched list first, so the
    // identity survives the client-side filters applied afterwards.
    let r = (invocations ?? []).map((inv, i) => ({ ...inv, _id: `${inv.timestamp}-${i}` }));
    if (until) r = r.filter((inv) => inv.timestamp <= until);
    if (q) r = r.filter((inv) => inv.capability_key.toLowerCase().includes(q));
    return r;
  }, [invocations, until, q]);

  if (isPending) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          {t("mcp.invocations.loading")}
        </CardContent>
      </Card>
    );
  }
  if (error) {
    return (
      <Card>
        <CardContent className="py-4">
          <p className="text-sm text-destructive">{translateApiError(t, error)}</p>
          <Button size="sm" variant="outline" className="mt-2" onClick={() => void refetch()}>
            {t("common.retry")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  const columns: Column<InvocationRow>[] = [
    {
      key: "time",
      header: t("mcp.invocations.header.time"),
      className: "text-xs text-muted-foreground",
      cell: (inv) => formatDateTime(inv.timestamp),
    },
    {
      key: "type",
      header: t("mcp.invocations.header.type"),
      cell: (inv) => <Badge variant="outline">{inv.capability_type}</Badge>,
    },
    {
      key: "key",
      header: t("mcp.invocations.header.key"),
      className: "font-mono text-xs",
      cell: (inv) => inv.capability_key,
    },
    {
      key: "duration",
      header: t("mcp.invocations.header.duration"),
      className: "text-right text-xs",
      cell: (inv) => `${inv.duration_ms} ms`,
    },
    {
      key: "status",
      header: t("mcp.invocations.header.status"),
      cell: (inv) => (
        <>
          <Badge className={invocationStatusClass(inv.status)} variant="outline">
            {inv.status}
          </Badge>
          {inv.error_message ? (
            <div className="mt-0.5 text-xs text-muted-foreground">{inv.error_message}</div>
          ) : null}
        </>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <InvocationsFilters state={filters} onChange={setFilters} />

      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(inv) => inv._id}
        getRowDetail={(inv) => (
          <div className="px-4 py-3">
            {/* Strip the synthetic _id so the raw log shows the daemon's record verbatim. */}
            <RawLog record={stripId(inv)} />
          </div>
        )}
        // `allRows.length === 0` = nothing recorded yet; any rows present but
        // filtered out = a no-matches state. DataTable renders one emptyMessage,
        // so pick the right one based on whether the fetch returned anything.
        emptyMessage={
          allRows.length === 0 ? t("mcp.invocations.empty") : t("mcp.invocations.noMatches")
        }
      />
    </div>
  );
}
