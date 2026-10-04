// src/components/activity/activityCells.tsx — how one Activity record reads in a row: its time, icon, sentence, who and duration.
//
// Shared by the list and the drawer so a record says the same thing in both.
// Logs are tabular, so rows stay dense: times and identifiers in mono, a
// failure in its status colour beside the call it belongs to.
import type { TFunction } from "i18next";
import { PencilLine, ScrollText, Server, type LucideIcon } from "lucide-react";

import { StatusWord } from "@/components/status/StatusWord";
import type { StatusTone } from "@/lib/statusTone";
import { describeActivity, describeDaemonRecord } from "@/lib/activity/activityText";
import {
  callServerLabel,
  daemonLevel,
  formatDuration,
  recordLogger,
  recordSeverity,
  type ActivityRecord,
  type Invocation,
} from "@/lib/activity/records";
import { actorLabel, callOutcome, clockTime } from "@/lib/activity/recordText";
import { cn } from "@/lib/utils";

/** @ui-only An agent as a row shows it. */
export interface AgentLook {
  type: string;
  name: string;
}

export function TimeCell({ at, withMs = false }: { at: string | null; withMs?: boolean }) {
  return (
    <time
      dateTime={at ?? undefined}
      className="whitespace-nowrap font-mono text-xs text-text-muted"
    >
      {clockTime(at, withMs)}
    </time>
  );
}

const SOURCE_ICON: Record<ActivityRecord["source"], LucideIcon> = {
  change: PencilLine,
  call: Server,
  daemon: ScrollText,
};

/** The record's source as a small tile, toned by how serious it is. */
export function SourceIcon({ record }: { record: ActivityRecord }) {
  const Icon = SOURCE_ICON[record.source];
  const severity = recordSeverity(record);
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-[22px] shrink-0 items-center justify-center rounded-sm",
        severity === "error"
          ? "bg-danger-soft text-danger"
          : severity === "warning"
            ? "bg-warning-soft text-warning"
            : "bg-surface-sunken text-text-muted",
      )}
    >
      <Icon className="size-3.5" strokeWidth={1.75} />
    </span>
  );
}

/** The call's target, `server.tool`, in mono; the Tool calls table mutes the server part. */
export function CallTarget({
  call,
  className,
  muteServer = false,
}: {
  call: Invocation;
  className?: string;
  muteServer?: boolean;
}) {
  return (
    <span
      data-call-target
      className={cn("whitespace-nowrap font-mono text-xs text-text", className)}
    >
      {muteServer ? (
        <span className="text-text-muted">{callServerLabel(call)}.</span>
      ) : (
        `${callServerLabel(call)}.`
      )}
      {call.capability_key}
    </span>
  );
}

/** One line saying what happened, for the Everything and Changes tabs. */
export function EventCell({ t, record }: { t: TFunction; record: ActivityRecord }) {
  if (record.source === "call") {
    const outcome = callOutcome(t, record.call);
    return (
      <span className="block min-w-0 truncate text-sm">
        <CallTarget call={record.call} />
        {outcome ? (
          <span
            className={cn(
              "ml-1.5",
              record.call.status === "error" ? "text-danger" : "text-warning",
            )}
          >
            {outcome}
          </span>
        ) : null}
      </span>
    );
  }
  if (record.source === "change") {
    return (
      <span className="block min-w-0 truncate text-sm text-text">
        {describeActivity(t, record.entry)}
      </span>
    );
  }
  const logger = recordLogger(record);
  return (
    <span className="block min-w-0 truncate text-sm text-text">
      {logger ? <span className="mr-1.5 font-mono text-xs text-text-muted">{logger}</span> : null}
      {describeDaemonRecord(t, record.log)}
    </span>
  );
}

/** Who did it: an agent's name for a call, the actor for a change, Coffer for the daemon. */
export function ByCell({
  t,
  record,
  agents,
}: {
  t: TFunction;
  record: ActivityRecord;
  agents: ReadonlyMap<string, AgentLook>;
}) {
  if (record.source === "call") {
    const agent = record.call.agent_uid ? agents.get(record.call.agent_uid) : undefined;
    return agent ? (
      <span className="block truncate text-xs text-text">{agent.name}</span>
    ) : (
      <span className="text-xs text-text-subtle">—</span>
    );
  }
  const text =
    record.source === "change" ? actorLabel(t, record.entry.actor) : actorLabel(t, "system");
  return <span className="block truncate text-xs text-text-muted">{text}</span>;
}

export function TookCell({ record }: { record: ActivityRecord }) {
  if (record.source !== "call") return null;
  return (
    <span className="block whitespace-nowrap text-right font-mono text-xs text-text-muted">
      {formatDuration(record.call.duration_ms)}
    </span>
  );
}

const STATUS_TONE: Record<Invocation["status"], StatusTone> = {
  ok: "ok",
  error: "err",
  timeout: "warn",
  denied: "off",
};

export function CallStatus({ t, call }: { t: TFunction; call: Invocation }) {
  return (
    <StatusWord tone={STATUS_TONE[call.status]}>{t(`activity.status.${call.status}`)}</StatusWord>
  );
}

/** A daemon record's level as plain mono text: grey, except a warning (amber) and an error (red). */
export function LevelText({ record }: { record: ActivityRecord }) {
  if (record.source !== "daemon") return null;
  const level = daemonLevel(record.log);
  if (!level) return <span className="text-xs text-text-subtle">—</span>;
  const severity = recordSeverity(record);
  return (
    <span
      className={cn(
        "font-mono text-xs",
        severity === "error"
          ? "text-danger"
          : severity === "warning"
            ? "text-warning"
            : "text-text-muted",
      )}
    >
      {level}
    </span>
  );
}

/** A daemon record's level as a coloured word ("—" when the line stated none). */
export function LevelWord({ record }: { record: ActivityRecord }) {
  if (record.source !== "daemon") return null;
  const level = daemonLevel(record.log);
  if (!level) return <span className="text-xs text-text-subtle">—</span>;
  const severity = recordSeverity(record);
  return (
    <span
      className={cn(
        "font-mono text-2xs font-semibold uppercase",
        severity === "error"
          ? "text-danger"
          : severity === "warning"
            ? "text-warning"
            : "text-text-muted",
      )}
    >
      {level}
    </span>
  );
}
