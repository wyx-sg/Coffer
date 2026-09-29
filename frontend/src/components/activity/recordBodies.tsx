// src/components/activity/recordBodies.tsx — what each kind of Activity record shows in the drawer: a change, a call, a daemon record.
//
// Split from RecordDrawer, which is the frame (title, stepping, facts around
// the body, actions); this file is the body each record source brings.
import type { ReactNode } from "react";
import type { TFunction } from "i18next";
import { ShieldCheck } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { describeDaemonRecord } from "@/lib/activity/activityText";
import {
  callServerLabel,
  formatDuration,
  recordLogger,
  type ActivityRecord,
  type AuditEntry,
  type DaemonLogRecord,
  type Invocation,
} from "@/lib/activity/records";
import { actorLabel, callOutcome } from "@/lib/activity/recordText";
import { diffCounts, diffValues } from "@/lib/activity/valueDiff";
import { cn } from "@/lib/utils";
import { LevelWord, type AgentLook } from "./activityCells";
import { ValueDiffBlock } from "./ValueDiffBlock";

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

export function ChangeBody({ t, entry }: { t: TFunction; entry: AuditEntry }) {
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
            <ValueDiffBlock lines={lines} />
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

export function CallBody({
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

export function DaemonBody({
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
