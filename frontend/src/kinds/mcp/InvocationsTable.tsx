// frontend/src/kinds/mcp/InvocationsTable.tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
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
import { useMcpInvocations } from "@/lib/hooks/useMcpInvocations";
import { translateApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/utils";
import { InvocationsFilters, type InvocationsFiltersState } from "./InvocationsFilters";

interface Props {
  serverName: string;
}

const STATUS_COLOURS: Record<string, string> = {
  ok: "bg-green-100 text-green-900 dark:bg-green-950 dark:text-green-200",
  error: "bg-destructive/10 text-destructive",
  timeout: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  denied: "bg-muted text-muted-foreground",
};

const RANGE_MS: Record<string, number> = {
  "1h": 3_600_000,
  "6h": 21_600_000,
  "24h": 86_400_000,
  "7d": 604_800_000,
  "30d": 2_592_000_000,
};

/** Typed "YYYY-MM-DD HH:mm:ss" -> ISO string; empty/invalid -> undefined. */
function parseDateTime(value: string): string | undefined {
  const v = value.trim();
  if (!v) return undefined;
  const d = new Date(v.replace(" ", "T"));
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString();
}

/** Resolve the active time filter state to a `since` ISO string. */
function resolveSince(filters: InvocationsFiltersState): string | undefined {
  if (filters.timeRange === "custom") {
    return parseDateTime(filters.from);
  }
  const ms = RANGE_MS[filters.timeRange];
  return ms ? new Date(Date.now() - ms).toISOString() : undefined;
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

  const since = resolveSince(filters);

  const { data, isPending, error, refetch } = useMcpInvocations({
    serverName,
    status: filters.status === "all" ? undefined : filters.status,
    since,
  });

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

  const allRows = data?.invocations ?? [];

  // Client-side search by capability_key
  const q = filters.search.trim().toLowerCase();
  const rows = q ? allRows.filter((inv) => inv.capability_key.toLowerCase().includes(q)) : allRows;

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
                {rows.map((inv, i) => (
                  <TableRow key={`${inv.timestamp}-${i}`}>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateTime(inv.timestamp)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{inv.capability_type}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{inv.capability_key}</TableCell>
                    <TableCell className="text-right text-xs">{inv.duration_ms} ms</TableCell>
                    <TableCell>
                      <Badge className={STATUS_COLOURS[inv.status] ?? ""} variant="outline">
                        {inv.status}
                      </Badge>
                      {inv.error_message ? (
                        <div className="mt-0.5 text-xs text-muted-foreground">
                          {inv.error_message}
                        </div>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
