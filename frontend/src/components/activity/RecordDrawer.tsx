// src/components/activity/RecordDrawer.tsx — one Activity record opened beside the list: the answer first, then context, then the next step.
//
// A failed call leads with its error; a change with what it changed (the
// config before and after, as a diff); a daemon record with its message and
// traceback. Below come the facts (who, which server, how long, which id),
// the records written around the same time, and the record's raw JSON. The
// drawer steps to the previous or next record without closing.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronUp, Copy, ExternalLink, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { RawLog } from "@/components/RawLog";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { describeActivity } from "@/lib/activity/activityText";
import { recordLogger, recordTimeMs, type ActivityRecord } from "@/lib/activity/records";
import { formatDateTime } from "@/lib/utils";
import { CallStatus, CallTarget, EventCell, SourceIcon, type AgentLook } from "./activityCells";
import { changeLink } from "@/lib/activity/recordText";
import { CallBody, ChangeBody, DaemonBody } from "./recordBodies";

const LABEL = "text-2xs font-semibold uppercase tracking-[.04em] text-text-subtle";

function nearby(record: ActivityRecord, rows: readonly ActivityRecord[]): ActivityRecord[] {
  const at = recordTimeMs(record.at);
  if (!at) return [];
  return rows
    .filter((r) => r.key !== record.key && r.at && Math.abs(recordTimeMs(r.at) - at) <= 60_000)
    .sort((a, b) => Math.abs(recordTimeMs(a.at) - at) - Math.abs(recordTimeMs(b.at) - at))
    .slice(0, 3);
}

function offsetLabel(from: ActivityRecord, to: ActivityRecord): string {
  const seconds = Math.round((recordTimeMs(to.at) - recordTimeMs(from.at)) / 1000);
  return seconds >= 0 ? `+${seconds} s` : `−${Math.abs(seconds)} s`;
}

function titleOf(t: TFunction, record: ActivityRecord): ReactNode {
  if (record.source === "call") return <CallTarget call={record.call} className="text-sm" />;
  if (record.source === "change") return describeActivity(t, record.entry);
  return recordLogger(record) || t("activity.drawer.kinds.daemon");
}

interface Props {
  record: ActivityRecord;
  /** The rows on screen, for previous / next and "around the same time". */
  rows: readonly ActivityRecord[];
  agents: ReadonlyMap<string, AgentLook>;
  onSelect: (key: string) => void;
  onClose: () => void;
}

export function RecordDrawer({ record, rows, agents, onSelect, onClose }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const index = rows.findIndex((r) => r.key === record.key);
  const previous = index > 0 ? rows[index - 1] : undefined;
  const next = index >= 0 && index < rows.length - 1 ? rows[index + 1] : undefined;
  const around = nearby(record, rows);

  const raw =
    record.source === "change"
      ? record.entry
      : record.source === "call"
        ? record.call
        : record.log.record;

  const copy = (text: string) => {
    void navigator.clipboard
      ?.writeText(text)
      .then(() => toast.success(t("activity.drawer.copied")))
      .catch(() => toast.error(t("activity.drawer.copyFailed")));
  };

  const link =
    record.source === "change"
      ? changeLink(record.entry)
      : record.source === "call" && record.call.resource_name
        ? {
            to: `/mcp-servers/${encodeURIComponent(record.call.resource_uid)}`,
            name: record.call.resource_name,
          }
        : null;

  return (
    <aside
      aria-label={t("activity.drawer.label")}
      className="flex h-full w-full flex-col border-l border-border bg-surface-raised md:w-[420px] md:shrink-0"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <header className="flex flex-col gap-1.5 border-b border-border-subtle px-5 pb-3 pt-4">
        <div className="flex items-start gap-2">
          <h2 className="min-w-0 flex-1 break-words text-md font-semibold text-text">
            {titleOf(t, record)}
          </h2>
          <span className="flex shrink-0 items-center gap-0.5">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t("activity.drawer.previous")}
              disabled={!previous}
              onClick={() => previous && onSelect(previous.key)}
            >
              <ChevronUp />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t("activity.drawer.next")}
              disabled={!next}
              onClick={() => next && onSelect(next.key)}
            >
              <ChevronDown />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t("activity.drawer.close")}
              onClick={onClose}
            >
              <X />
            </Button>
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-text-muted">
          {record.source === "call" ? (
            <CallStatus t={t} call={record.call} />
          ) : (
            <span>{t(`activity.drawer.kinds.${record.source}`)}</span>
          )}
          {record.at ? <time dateTime={record.at}>{formatDateTime(record.at)}</time> : null}
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
        {record.source === "change" ? <ChangeBody t={t} entry={record.entry} /> : null}
        {record.source === "call" ? <CallBody t={t} call={record.call} agents={agents} /> : null}
        {record.source === "daemon" ? <DaemonBody t={t} log={record.log} record={record} /> : null}

        {around.length ? (
          <section className="flex flex-col gap-1.5">
            <span className={LABEL}>{t("activity.drawer.around")}</span>
            {around.map((r) => (
              <button
                key={r.key}
                type="button"
                onClick={() => onSelect(r.key)}
                className="flex items-center gap-2 rounded-md px-1.5 py-1 text-left hover:bg-surface-hover"
              >
                <SourceIcon record={r} />
                <span className="min-w-0 flex-1">
                  <EventCell t={t} record={r} />
                </span>
                <span className="shrink-0 font-mono text-2xs text-text-subtle">
                  {offsetLabel(record, r)}
                </span>
              </button>
            ))}
          </section>
        ) : null}

        <RawLog record={raw} />
      </div>

      <footer className="flex flex-wrap items-center gap-2 border-t border-border-subtle px-5 py-3">
        {link ? (
          <Button asChild variant="outline" size="sm">
            <Link to={link.to}>
              <ExternalLink />
              {t("activity.drawer.open", { name: link.name })}
            </Link>
          </Button>
        ) : null}
        {record.source === "call" ? (
          <Button variant="outline" size="sm" onClick={() => copy(String(record.call.id))}>
            <Copy />
            {t("activity.drawer.copyCallId")}
          </Button>
        ) : (
          <Button variant="outline" size="sm" onClick={() => copy(JSON.stringify(raw, null, 2))}>
            <Copy />
            {t(
              record.source === "change"
                ? "activity.drawer.copyDetails"
                : "activity.drawer.copyRecord",
            )}
          </Button>
        )}
      </footer>
    </aside>
  );
}
