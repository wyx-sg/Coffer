// src/components/activity/recordBodies.tsx — what each kind of Activity record shows in the drawer: a change, a call, a daemon record.
//
// Split from RecordDrawer, which is the frame (title, stepping, what else
// happened around it, actions); this file is the body each record source
// brings. Answer first: a failed call leads with its error and how its server
// has been doing, a change with who made it and what it touched, then its
// before and after as a diff (design 6.2.01). A change whose event
// this page has no words for — a new kind of record — still reads through the same facts and diff.
import type { ReactNode } from "react";
import type { TFunction } from "i18next";
import { AlertCircle, AlertTriangle, Info, ShieldCheck } from "lucide-react";

import { Section } from "@/components/Section";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { daemonContinuation, describeDaemonRecord } from "@/lib/activity/activityText";
import {
  callServerLabel,
  formatDuration,
  recordLogger,
  type ActivityRecord,
  type AuditEntry,
  type DaemonLogRecord,
  type Invocation,
} from "@/lib/activity/records";
import { actorLong, callProblemTitle, serverFailureLine } from "@/lib/activity/recordText";
import { changedFields, diffCounts, diffValues } from "@/lib/activity/valueDiff";
import type { ServerFailures } from "@/lib/hooks/useServerFailures";
import { cn } from "@/lib/utils";
import { LevelWord, type AgentLook } from "./activityCells";
import { ValueDiffBlock } from "./ValueDiffBlock";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[96px_minmax(0,1fr)] items-baseline gap-x-3 py-1">
      <span className="text-xs text-text-subtle">{label}</span>
      <span className="min-w-0 break-words text-sm text-text">{children}</span>
    </div>
  );
}

function Mono({ children, muted = false }: { children: ReactNode; muted?: boolean }) {
  return (
    <span className={cn("font-mono text-xs", muted ? "text-text-muted" : "text-text")}>
      {children}
    </span>
  );
}

/** The request's or turn's correlation id: the key that joins an audit row,
 * an MCP call and the daemon log lines of the same request or turn. */
function TraceFact({ t, traceId }: { t: TFunction; traceId: string | null | undefined }) {
  if (!traceId) return null;
  return (
    <Fact label={t("activity.drawer.trace")}>
      <Mono muted>{traceId}</Mono>
    </Fact>
  );
}

function Aside({ children }: { children: ReactNode }) {
  return <span className="text-xs text-text-subtle">{children}</span>;
}

export function ChangeBody({ t, entry }: { t: TFunction; entry: AuditEntry }) {
  const details = (entry.details ?? {}) as Record<string, unknown>;
  const hasDiff = "before" in details || "after" in details;
  const lines = hasDiff ? diffValues(details.before, details.after) : [];
  const counts = diffCounts(lines);
  const fields = hasDiff ? changedFields(details.before, details.after) : [];
  return (
    <>
      <div>
        <Fact label={t("activity.drawer.who")}>{actorLong(t, entry.actor)}</Fact>
        {entry.resource_kind || entry.resource_name ? (
          <Fact label={t("activity.drawer.what")}>
            {entry.resource_kind
              ? t(`activity.drawer.kindNames.${entry.resource_kind}`, {
                  defaultValue: entry.resource_kind,
                })
              : null}
            {entry.resource_name ? (
              <>
                {" "}
                <Mono>{entry.resource_name}</Mono>
              </>
            ) : null}
            {fields.length ? (
              <>
                {" "}
                <Aside>· {fields.join(", ")}</Aside>
              </>
            ) : null}
          </Fact>
        ) : null}
        <TraceFact t={t} traceId={entry.trace_id} />
      </div>
      {hasDiff ? (
        <Section
          title={t("activity.drawer.whatChanged")}
          gap="snug"
          className="min-w-0"
          actions={
            lines.length ? (
              <span className="flex gap-1.5 font-mono text-2xs">
                <span className="text-success">+{counts.added}</span>
                <span className="text-danger">−{counts.removed}</span>
              </span>
            ) : null
          }
        >
          {lines.length ? (
            <ValueDiffBlock lines={lines} />
          ) : (
            <p className="text-sm text-text-muted">{t("activity.drawer.noDiff")}</p>
          )}
          <p className="inline-flex items-center gap-1.5 text-xs text-text-subtle">
            <ShieldCheck className="size-3.5" aria-hidden />
            {t("activity.drawer.secretNote")}
          </p>
        </Section>
      ) : null}
    </>
  );
}

export function CallBody({
  t,
  call,
  agents,
  transport,
  failures,
}: {
  t: TFunction;
  call: Invocation;
  agents: ReadonlyMap<string, AgentLook>;
  /** The server's transport, when the server still exists. */
  transport: "stdio" | "http" | "unknown" | undefined;
  failures: ServerFailures | undefined;
}) {
  const agent = call.agent_uid ? agents.get(call.agent_uid) : undefined;
  const failed = call.status === "error" || call.status === "timeout";
  const outcome = [call.error_message, serverFailureLine(t, call, failures)]
    .filter(Boolean)
    .join(call.error_message?.endsWith(".") ? " " : ". ");
  const session = call.session_id;
  return (
    <>
      {call.status !== "ok" ? (
        <div
          role="alert"
          className={cn(
            "flex gap-2.5 rounded-lg border px-3.5 py-3",
            failed ? "border-danger/25 bg-danger-soft" : "border-warning/30 bg-warning-soft",
          )}
        >
          {failed ? (
            <AlertCircle className="mt-px size-[15px] shrink-0 text-danger" aria-hidden />
          ) : (
            <AlertTriangle className="mt-px size-[15px] shrink-0 text-warning" aria-hidden />
          )}
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="text-sm font-label text-text">{callProblemTitle(t, call)}</span>
            {outcome ? (
              <span className="text-xs leading-[1.45] text-text-muted">{outcome}</span>
            ) : null}
            {call.handoff ? (
              <span className="mt-2">
                <AgentHandoff prompt={call.handoff.prompt} size="sm" />
              </span>
            ) : null}
          </div>
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
          {session ? (
            <span title={session}>
              <Mono>{session.length > 13 ? session.slice(0, 13) : session}</Mono>
            </span>
          ) : (
            <span className="text-text-muted">—</span>
          )}
        </Fact>
        <Fact label={t("activity.drawer.server")}>
          <Mono>{callServerLabel(call)}</Mono>
          {transport && transport !== "unknown" ? (
            <>
              {" "}
              <Aside>· {t(`mcp.page.transport.${transport}`)}</Aside>
            </>
          ) : null}
        </Fact>
        <Fact label={t(`activity.drawer.capability.${call.capability_type}`)}>
          <Mono>{call.capability_key}</Mono>
        </Fact>
        <Fact label={t("activity.drawer.took")}>{formatDuration(call.duration_ms)}</Fact>
        <Fact label={t("activity.drawer.callId")}>
          <Mono muted>{call.id}</Mono>
        </Fact>
        <TraceFact t={t} traceId={call.trace_id} />
      </div>
      <p className="flex items-start gap-1.5 text-xs leading-[1.45] text-text-muted">
        <Info className="mt-px size-3.5 shrink-0 text-text-subtle" aria-hidden />
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
  const lines = daemonContinuation(log);
  return (
    <>
      <p className="break-words font-mono text-xs text-text">{describeDaemonRecord(t, log)}</p>
      {lines.length ? (
        <pre className="max-h-64 overflow-auto rounded-lg border border-border-subtle bg-surface-sunken p-3 font-mono text-xs leading-[1.6] text-text">
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
