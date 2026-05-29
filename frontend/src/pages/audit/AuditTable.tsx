import { Fragment, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, ChevronUp } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { components } from "@/lib/api/types";
import { formatDateTime } from "@/lib/utils";
import { describeActivity } from "./auditText";

type AuditEntry = components["schemas"]["AuditEntryOut"];

interface Props {
  entries: AuditEntry[];
  /** Current timestamp sort direction. */
  sortDir: "asc" | "desc";
  /** Toggle the timestamp sort (newest-first <-> oldest-first). */
  onToggleSort: () => void;
}

/**
 * The audit log as a plain-language activity stream: each row is one
 * readable sentence ("Enabled demo-fs", "Discovered tool write_file …"),
 * not a raw `event_type` code. Clicking a row expands an exact detail
 * panel; clicking the Time header toggles newest/oldest-first.
 */
export function AuditTable({ entries, sortDir, onToggleSort }: Props) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const toggle = (id: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  if (entries.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          {t("audit.emptyState")}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8"></TableHead>
              <TableHead className="w-44">
                <button
                  type="button"
                  onClick={onToggleSort}
                  title={t("audit.table.sortByTime")}
                  className="flex items-center gap-1 font-medium transition-colors hover:text-foreground"
                >
                  {t("audit.table.time")}
                  {sortDir === "desc" ? (
                    <ChevronDown className="size-3.5" />
                  ) : (
                    <ChevronUp className="size-3.5" />
                  )}
                </button>
              </TableHead>
              <TableHead>{t("audit.table.activity")}</TableHead>
              <TableHead className="w-28">{t("audit.table.actor")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map((entry) => {
              const details = (entry.details ?? {}) as Record<string, unknown>;
              const activity = describeActivity(t, entry);
              const isOpen = expanded.has(entry.id);
              return (
                <Fragment key={entry.id}>
                  <TableRow className="cursor-pointer" onClick={() => toggle(entry.id)}>
                    <TableCell className="text-muted-foreground">
                      {isOpen ? (
                        <ChevronDown className="size-4" />
                      ) : (
                        <ChevronRight className="size-4" />
                      )}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatDateTime(entry.timestamp)}
                    </TableCell>
                    <TableCell className="text-sm">{activity}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {t(`audit.actor.${entry.actor}`, {
                        defaultValue: entry.actor,
                      })}
                    </TableCell>
                  </TableRow>
                  {isOpen ? (
                    <TableRow className="bg-muted/30 hover:bg-muted/30">
                      <TableCell />
                      <TableCell colSpan={3} className="py-3">
                        <DetailPanel entry={entry} details={details} />
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
  );
}

function DetailPanel({ entry, details }: { entry: AuditEntry; details: Record<string, unknown> }) {
  const { t } = useTranslation();
  const payload = Object.entries(details);
  return (
    <div className="space-y-1.5 text-xs">
      <Field label={t("audit.detail.time")} value={formatDateTime(entry.timestamp)} />
      <Field
        label={t("audit.detail.event")}
        value={t(`audit.eventLabel.${entry.event_type}`, {
          defaultValue: entry.event_type,
        })}
      />
      {entry.resource_kind && entry.resource_name ? (
        <Field
          label={t("audit.detail.resource")}
          value={`${entry.resource_kind}:${entry.resource_name}`}
        />
      ) : null}
      <Field
        label={t("audit.detail.actor")}
        value={t(`audit.actor.${entry.actor}`, { defaultValue: entry.actor })}
      />
      <div className="pt-1">
        <div className="mb-1 font-medium text-muted-foreground">{t("audit.detail.payload")}</div>
        {payload.length === 0 ? (
          <div className="text-muted-foreground">{t("audit.detail.empty")}</div>
        ) : (
          <div className="space-y-1">
            {payload.map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <span className="shrink-0 font-mono text-muted-foreground">{k}</span>
                <span className="break-all font-mono">
                  {typeof v === "object" ? JSON.stringify(v) : String(v)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="w-20 shrink-0 text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  );
}
