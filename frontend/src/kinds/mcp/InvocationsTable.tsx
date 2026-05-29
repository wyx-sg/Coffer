// frontend/src/kinds/mcp/InvocationsTable.tsx
import { Fragment, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RawLog } from "@/components/RawLog";
import { useMcpInvocations } from "@/lib/hooks/useMcpInvocations";
import { translateApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/utils";
import { resolveTimeWindow } from "@/lib/timeRange";
import { invocationStatusClass } from "@/lib/statusColors";
import { InvocationsFilters, type InvocationsFiltersState } from "./InvocationsFilters";

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

export function InvocationsTable({ serverName }: Props) {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<InvocationsFiltersState>(DEFAULT_FILTERS);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

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
  const rows = useMemo(() => {
    let r = invocations ?? [];
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

  // No invocations at all (before filtering)
  if (allRows.length === 0) {
    return (
      <div className="space-y-3">
        <Card>
          <CardContent className="py-4">
            <InvocationsFilters state={filters} onChange={setFilters} />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("mcp.invocations.empty")}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Card>
        <CardContent className="py-4">
          <InvocationsFilters state={filters} onChange={setFilters} />
        </CardContent>
      </Card>

      {rows.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("mcp.invocations.noMatches")}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8"></TableHead>
                  <TableHead>{t("mcp.invocations.header.time")}</TableHead>
                  <TableHead>{t("mcp.invocations.header.type")}</TableHead>
                  <TableHead>{t("mcp.invocations.header.key")}</TableHead>
                  <TableHead className="text-right">
                    {t("mcp.invocations.header.duration")}
                  </TableHead>
                  <TableHead>{t("mcp.invocations.header.status")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((inv, i) => {
                  const id = `${inv.timestamp}-${i}`;
                  const isOpen = expanded.has(id);
                  return (
                    <Fragment key={id}>
                      <TableRow
                        className="cursor-pointer"
                        tabIndex={0}
                        aria-expanded={isOpen}
                        onClick={() => toggle(id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggle(id);
                          }
                        }}
                      >
                        <TableCell className="text-muted-foreground">
                          {isOpen ? (
                            <ChevronDown className="size-4" />
                          ) : (
                            <ChevronRight className="size-4" />
                          )}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {formatDateTime(inv.timestamp)}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{inv.capability_type}</Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{inv.capability_key}</TableCell>
                        <TableCell className="text-right text-xs">{inv.duration_ms} ms</TableCell>
                        <TableCell>
                          <Badge className={invocationStatusClass(inv.status)} variant="outline">
                            {inv.status}
                          </Badge>
                          {inv.error_message ? (
                            <div className="mt-0.5 text-xs text-muted-foreground">
                              {inv.error_message}
                            </div>
                          ) : null}
                        </TableCell>
                      </TableRow>
                      {isOpen ? (
                        <TableRow className="bg-muted/30 hover:bg-muted/30">
                          <TableCell />
                          <TableCell colSpan={5} className="py-3">
                            <RawLog record={inv} />
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
