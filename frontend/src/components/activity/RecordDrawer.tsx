// src/components/activity/RecordDrawer.tsx — one Activity record opened beside the list: the answer first, then context, then the next step.
//
// A failed call leads with its error; a change with who made it and what it
// changed (the config before and after, as a diff); a daemon record with its
// message and traceback. Below come the records written around the same time
// and the record's raw JSON, and the footer holds the next step: open the
// resource, read the daemon's records about a failing server, or copy the
// record. The drawer steps to the previous or next record without closing.
// An MCP call shows its metadata only: Coffer never stores a call's arguments
// or results (design 6.1.08).
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Section } from "@/components/Section";
import { ChevronDown, ChevronUp, Copy, ExternalLink, ScrollText, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { RawLog } from "@/components/RawLog";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { describeActivity } from "@/lib/activity/activityText";
import { recordLogger, type ActivityRecord } from "@/lib/activity/records";
import { useKindPageOpen } from "@/lib/hooks/useFeatures";
import { changeLink, nearby, offsetLabel, whenLabel } from "@/lib/activity/recordText";
import { useServerFailures } from "@/lib/hooks/useServerFailures";
import {
  CallStatusChip,
  CallTarget,
  EventCell,
  LevelChip,
  SourceIcon,
  type AgentLook,
} from "./activityCells";
import { CallBody, ChangeBody, DaemonBody } from "./recordBodies";

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
  /** MCP server uid → its transport. */
  transports: ReadonlyMap<string, "stdio" | "http" | "unknown">;
  onSelect: (key: string) => void;
  onClose: () => void;
  /** Read the daemon's records about a server (a failed call's next step). */
  onDaemonRecords: (server: string) => void;
}

export function RecordDrawer({
  record,
  rows,
  agents,
  transports,
  onSelect,
  onClose,
  onDaemonRecords,
}: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const index = rows.findIndex((r) => r.key === record.key);
  const previous = index > 0 ? rows[index - 1] : undefined;
  const next = index >= 0 && index < rows.length - 1 ? rows[index + 1] : undefined;
  const around = nearby(record, rows);
  const call = record.source === "call" ? record.call : null;
  const failures = useServerFailures(call);

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

  const pageOpen = useKindPageOpen();
  const link =
    record.source === "change"
      ? pageOpen(record.entry.resource_kind ?? "")
        ? changeLink(record.entry)
        : null
      : call?.resource_name
        ? { to: `/mcp-servers/${encodeURIComponent(call.resource_name)}`, name: call.resource_name }
        : null;

  let secondary: ReactNode;
  if (call && call.status !== "ok") {
    secondary = (
      <Button
        variant="ghost"
        size="default"
        onClick={() => onDaemonRecords(call.resource_name ?? call.resource_uid)}
      >
        <ScrollText />
        {t("activity.drawer.daemonRecords")}
      </Button>
    );
  } else if (call) {
    secondary = (
      <Button variant="ghost" size="default" onClick={() => copy(String(call.id))}>
        <Copy />
        {t("activity.drawer.copyCallId")}
      </Button>
    );
  } else {
    secondary = (
      <Button variant="ghost" size="default" onClick={() => copy(JSON.stringify(raw, null, 2))}>
        <Copy />
        {t(
          record.source === "change" ? "activity.drawer.copyDetails" : "activity.drawer.copyRecord",
        )}
      </Button>
    );
  }

  return (
    <aside
      aria-label={t("activity.drawer.label")}
      className="flex h-full w-full flex-col border-l border-border bg-surface-raised md:w-[400px] md:shrink-0"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <header className="flex flex-col gap-2 border-b border-border-subtle px-5 pb-3.5 pt-[18px]">
        <div className="flex items-center gap-2">
          <h2 className="min-w-0 flex-1 truncate text-md font-bold text-text">
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
        <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
          {call ? (
            <CallStatusChip t={t} call={call} />
          ) : record.source === "daemon" ? (
            <LevelChip record={record} />
          ) : (
            <span className="inline-flex h-5 items-center rounded-sm bg-chip px-[7px] text-2xs font-label">
              {t("activity.drawer.kinds.change")}
            </span>
          )}
          {record.at ? (
            <time dateTime={record.at}>
              {whenLabel(t, record.at, record.source !== "change", i18n.language)}
            </time>
          ) : null}
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-[18px] overflow-y-auto px-5 py-4">
        {record.source === "change" ? <ChangeBody t={t} entry={record.entry} /> : null}
        {call ? (
          <CallBody
            t={t}
            call={call}
            agents={agents}
            transport={transports.get(call.resource_uid)}
            failures={failures}
          />
        ) : null}
        {record.source === "daemon" ? <DaemonBody t={t} log={record.log} record={record} /> : null}

        {around.length ? (
          <Section title={t("activity.drawer.around")} gap="tight">
            <div className="flex flex-col">
              {around.map((r, i) => (
                <button
                  key={r.key}
                  type="button"
                  onClick={() => onSelect(r.key)}
                  className={
                    "flex min-h-[34px] items-center gap-2.5 text-left hover:bg-surface-hover" +
                    (i > 0 ? " border-t border-border-subtle" : "")
                  }
                >
                  <SourceIcon record={r} />
                  <span className="min-w-0 flex-1">
                    <EventCell t={t} record={r} />
                  </span>
                  <span className="shrink-0 font-mono text-xs text-text-muted">
                    {offsetLabel(t, record, r)}
                  </span>
                </button>
              ))}
            </div>
          </Section>
        ) : null}

        <RawLog record={raw} />
      </div>

      <footer className="flex flex-wrap items-center gap-2 border-t border-border px-5 py-3">
        {link ? (
          <Button asChild variant="outline" size="default">
            <Link to={link.to}>
              <ExternalLink />
              {t("activity.drawer.open", { name: link.name })}
            </Link>
          </Button>
        ) : null}
        {secondary}
      </footer>
    </aside>
  );
}
