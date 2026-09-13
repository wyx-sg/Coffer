// frontend/src/pages/activity/activityText.ts
//
// Every plain-language line the Activity tabs render, and the search haystack
// that must match it. The two are deliberately produced by the same functions:
// the old audit page split them once and the search box promptly stopped
// matching what the row actually said.
import type { TFunction } from "i18next";
import type { components } from "@/lib/api/types";

type AuditEntry = components["schemas"]["AuditEntryOut"];
type DaemonLogRecord = components["schemas"]["DaemonLogRecordOut"];

/** A capability type (tool / resource / prompt) in the reader's language. */
function capTypeLabel(t: TFunction, raw: string): string {
  return raw ? t(`audit.capType.${raw}`, { defaultValue: raw }) : "";
}

/**
 * Render one audit entry as a plain-language activity sentence — the same
 * text the Changes row shows. Event types are translated per locale (guarded
 * by `i18n/backend-keys.test.ts`) so a zh reader never sees a raw
 * `resource_enabled` on a row.
 */
export function describeActivity(t: TFunction, entry: AuditEntry): string {
  const details = (entry.details ?? {}) as Record<string, unknown>;
  const capTypeRaw = typeof details.capability_type === "string" ? details.capability_type : "";
  return t(`audit.activity.${entry.event_type}`, {
    defaultValue: entry.event_type,
    resource: entry.resource_name ?? "",
    key: typeof details.key === "string" ? details.key : "",
    capType: capTypeLabel(t, capTypeRaw),
  });
}

/**
 * The lowercased free-text haystack for one change — everything a user might
 * type into the Changes search box: the rendered sentence (so anything visible
 * is searchable by construction), the resource name, the raw event code a
 * reader may know from `coffer__diagnose`, and the humanised actor.
 */
export function auditSearchHaystack(t: TFunction, entry: AuditEntry): string {
  return [
    describeActivity(t, entry),
    entry.resource_name ?? "",
    entry.event_type,
    t(`audit.actor.${entry.actor}`, { defaultValue: entry.actor }),
  ]
    .join(" ")
    .toLowerCase();
}

/**
 * One daemon log record as a sentence: structlog's `event` field, falling back
 * to the verbatim line for a record that was not JSON — a traceback is not a
 * structlog record and is usually the line worth reading.
 */
export function describeDaemonRecord(t: TFunction, rec: DaemonLogRecord): string {
  const raw = rec.record?.raw;
  return rec.event || (typeof raw === "string" ? raw : "") || t("activity.daemon.noMessage");
}

/** The structlog logger that emitted a record, if the line carried one. */
export function daemonLogger(rec: DaemonLogRecord): string {
  const logger = rec.record?.logger;
  return typeof logger === "string" ? logger : "";
}

/**
 * The lowercased free-text haystack for one daemon record: the rendered
 * message, its logger and its level. A line that never parsed as JSON has
 * neither logger nor level — its whole text is the message, which the
 * rendered line already carries.
 */
export function daemonSearchHaystack(t: TFunction, rec: DaemonLogRecord): string {
  return [describeDaemonRecord(t, rec), daemonLogger(rec), rec.level ?? ""].join(" ").toLowerCase();
}
