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
import { RawLog } from "@/components/RawLog";
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
              const activity = describeActivity(t, entry);
              const isOpen = expanded.has(entry.id);
              return (
                <Fragment key={entry.id}>
                  <TableRow
                    className="cursor-pointer"
                    tabIndex={0}
                    aria-expanded={isOpen}
                    onClick={() => toggle(entry.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        toggle(entry.id);
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
                        <RawLog record={entry} />
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
