// src/pages/activity/RecordDrawer.tsx — one Activity record opened beside the list: the answer first, then context, then the next step.
//
// A failed call leads with its error; a change with what it changed (the
// config before and after, as a diff); a daemon record with its message and
// traceback. Below come the facts (who, which server, how long, which id),
// the records written around the same time, and the record's raw JSON. The
// drawer steps to the previous or next record without closing.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronUp, Copy, ExternalLink, ShieldCheck, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { RawLog } from "@/components/RawLog";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { describeActivity, describeDaemonRecord } from "@/lib/activity/activityText";
import {
  callServerLabel,
  formatDuration,
  recordLogger,
  recordTimeMs,
  type ActivityRecord,
  type AuditEntry,
  type DaemonLogRecord,
  type Invocation,
} from "@/lib/activity/records";
import { diffCounts, diffValues, type ValueDiffLine } from "@/lib/activity/valueDiff";
import { cn, formatDateTime } from "@/lib/utils";
import { actorLabel, callOutcome } from "@/lib/activity/recordText";
import {
  CallStatus,
  CallTarget,
  EventCell,
  LevelWord,
  SourceIcon,
  type AgentLook,
} from "./activityCells";

const LABEL = "text-2xs font-semibold uppercase tracking-[.04em] text-text-subtle";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[88px_minmax(0,1fr)] items-baseline gap-3 py-1">
      <span className="text-xs text-text-subtle">{label}</span>
      <span className="min-w-0 break-words text-sm text-text">{children}</span>
    </div>
  );
}

function Mono({ children }: { children: ReactNode }) {
  return <span className="font-mono text-xs">{children}</span>;
}

function DiffBlock({ lines }: { lines: ValueDiffLine[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface-raised font-mono text-xs leading-5">
      {lines.map((line, index) =>
        line.kind === "gap" ? (
          <div
            key={index}
            className="border-y border-border-subtle bg-surface-sunken px-3 text-text-subtle"
          >
            {line.text}
          </div>
        ) : (
          <div
            key={index}
            data-line={line.kind}
            className={cn(
              "grid grid-cols-[30px_30px_14px_minmax(0,1fr)]",
              line.kind === "add" && "bg-success-soft",
              line.kind === "remove" && "bg-danger-soft",
            )}
          >
            <span className="pr-1.5 text-right text-2xs text-text-subtle">{line.oldNo ?? ""}</span>
            <span className="border-r border-border-subtle pr-1.5 text-right text-2xs text-text-subtle">
              {line.newNo ?? ""}
            </span>
            <span
              aria-hidden
              className={cn(
                "text-center",
                line.kind === "add" ? "text-success" : line.kind === "remove" ? "text-danger" : "",
              )}
            >
              {line.kind === "add" ? "+" : line.kind === "remove" ? "−" : ""}
            </span>
            <span className="whitespace-pre pr-2 text-text">{line.text}</span>
          </div>
        ),
      )}
    </div>
  );
}

/** The route a change's resource lives at, when it has a page of its own. */
function changeLink(entry: AuditEntry): { to: string; name: string } | null {
  const name = entry.resource_name;
  if (!name) return null;
  switch (entry.resource_kind) {
    case "mcp_server":
      return { to: `/mcp-servers/${encodeURIComponent(name)}`, name };
    case "skill":
      return { to: `/skills/${encodeURIComponent(name)}`, name };
    case "agent":
      return { to: "/agents", name };
    case "provider":
      return { to: "/model-providers", name };
    case "channel":
      return { to: "/channels", name };
    case "knowledge":
      return { to: "/knowledge", name };
    case "memory":
      return { to: "/memory", name };
    default:
      return null;
  }
}

function ChangeBody({ t, entry }: { t: TFunction; entry: AuditEntry }) {
  const details = (entry.details ?? {}) as Record<string, unknown>;
  const hasDiff = "before" in details || "after" in details;
  const lines = hasDiff ? diffValues(details.before, details.after) : [];
  const counts = diffCounts(lines);
  return (
    <>
      <div>
        <Fact label={t("activity.drawer.who")}>{actorLabel(t, entry.actor)}</Fact>
        <Fact label={t("activity.drawer.what")}>
          {entry.resource_kind
            ? t(`activity.drawer.kindNames.${entry.resource_kind}`, {
                defaultValue: entry.resource_kind,
              })
            : "—"}
          {entry.resource_name ? (
            <>
              {" "}
              <Mono>{entry.resource_name}</Mono>
            </>
          ) : null}
        </Fact>
        <Fact label={t("activity.drawer.event")}>
          <Mono>{entry.event_type}</Mono>
        </Fact>
      </div>
      {hasDiff ? (
        <section className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <span className={LABEL}>{t("activity.drawer.whatChanged")}</span>
            {lines.length ? (
              <span className="ml-auto font-mono text-2xs">
                <span className="text-success">+{counts.added}</span>{" "}
                <span className="text-danger">−{counts.removed}</span>
              </span>
            ) : null}
          </div>
          {lines.length ? (
            <DiffBlock lines={lines} />
          ) : (
            <p className="text-sm text-text-muted">{t("activity.drawer.noDiff")}</p>
          )}
          <p className="inline-flex items-center gap-1.5 text-xs text-text-subtle">
            <ShieldCheck className="size-3.5" aria-hidden />
            {t("activity.drawer.secretNote")}
          </p>
        </section>
      ) : null}
    </>
  );
}

function CallBody({
  t,
  call,
  agents,
}: {
  t: TFunction;
  call: Invocation;
  agents: ReadonlyMap<string, AgentLook>;
}) {
  const agent = call.agent_uid ? agents.get(call.agent_uid) : undefined;
  const outcome = callOutcome(t, call);
  return (
    <>
      {call.status !== "ok" ? (
        <div
          role="alert"
          className={cn(
            "flex flex-col gap-1 rounded-lg px-3 py-2.5",
            call.status === "error" ? "bg-danger-soft" : "bg-warning-soft",
          )}
        >
          <span
            className={cn(
              "text-sm font-label",
              call.status === "error" ? "text-danger" : "text-warning",
            )}
          >
            {t(`activity.drawer.callProblem.${call.status}`, { server: callServerLabel(call) })}
          </span>
          {call.error_message ? (
            <span className="text-sm text-text">{call.error_message}</span>
          ) : null}
          {!call.error_message && outcome ? (
            <span className="text-sm text-text">{outcome}</span>
          ) : null}
        </div>
      ) : null}
      <div>
        <Fact label={t("activity.drawer.agent")}>
          {agent ? (
            <AgentBadge type={agent.type} name={agent.name} size="sm" showName tooltip={false} />
          ) : (
            <span className="text-text-muted">{t("activity.drawer.noAgent")}</span>
          )}
        </Fact>
        <Fact label={t("activity.drawer.session")}>
          {call.session_id ? (
            <Mono>{call.session_id}</Mono>
          ) : (
            <span className="text-text-muted">—</span>
          )}
        </Fact>
        <Fact label={t("activity.drawer.server")}>
          <Mono>{callServerLabel(call)}</Mono>
        </Fact>
        <Fact label={t(`activity.drawer.capability.${call.capability_type}`)}>
          <Mono>{call.capability_key}</Mono>
        </Fact>
        <Fact label={t("activity.drawer.took")}>{formatDuration(call.duration_ms)}</Fact>
        <Fact label={t("activity.drawer.callId")}>
          <Mono>{call.id}</Mono>
        </Fact>
      </div>
      <p className="rounded-lg bg-surface-sunken px-3 py-2 text-xs text-text-muted">
        {t("activity.drawer.callNote")}
      </p>
    </>
  );
}

function DaemonBody({
  t,
  log,
  record,
}: {
  t: TFunction;
  log: DaemonLogRecord;
  record: ActivityRecord;
}) {
  const continuation = log.record?.continuation;
  const lines = Array.isArray(continuation)
    ? continuation.filter((l): l is string => typeof l === "string")
    : [];
  return (
    <>
      <p className="break-words font-mono text-xs text-text">{describeDaemonRecord(t, log)}</p>
      {lines.length ? (
        <pre className="max-h-64 overflow-auto rounded-lg bg-surface-sunken p-3 font-mono text-2xs leading-5 text-text">
          {lines.join("\n")}
        </pre>
      ) : null}
      <div>
        <Fact label={t("activity.drawer.level")}>
          <LevelWord record={record} />
        </Fact>
        <Fact label={t("activity.drawer.logger")}>
          <Mono>{recordLogger(record) || "—"}</Mono>
        </Fact>
      </div>
    </>
  );
}

/** Records within a minute of this one, nearest first, at most three. */
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
