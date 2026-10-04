// frontend/src/lib/activity/activityText.ts
//
// Every plain-language line the Activity tabs render, and the search haystack
// that must match it. The two are deliberately produced by the same functions:
// the old audit page split them once and the search box promptly stopped
// matching what the row actually said.
import type { TFunction } from "i18next";
import i18n from "@/i18n";
import { agentTypeLabel } from "@/lib/agents/display";
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
  const text = (k: string) => (typeof details[k] === "string" ? (details[k] as string) : "");
  return t(`audit.activity.${entry.event_type}`, {
    defaultValue: entry.event_type,
    resource: entry.resource_name ?? "",
    key: text("key"),
    // The agent a skill was bound to or unbound from (`details.agent`, written
    // by the link reconciler); older rows carry none.
    agent: text("agent") ? agentTypeLabel(text("agent")) : t("audit.agentFallback"),
    command: text("command"),
    capType: capTypeLabel(t, capTypeRaw),
  });
}

/** Every audit event type the current locale words as a sentence. */
function knownEventTypes(): string[] {
  const bundle = i18n.getResourceBundle(i18n.resolvedLanguage ?? i18n.language, "translation") as
    | { audit?: { activity?: Record<string, string> } }
    | undefined;
  return Object.keys(bundle?.audit?.activity ?? {});
}

/**
 * The audit event types whose sentence, in the reader's language, contains
 * `text`. The sentence a row shows is composed here from the event type and
 * its details, so the database cannot search it; it searches the raw event
 * code, the resource, the actor and the details itself, and is told these
 * event types in addition (`q_type`).
 */
export function eventTypesMatching(t: TFunction, text: string): string[] {
  const needle = text.trim().toLowerCase();
  if (!needle) return [];
  return knownEventTypes().filter((eventType) =>
    describeActivity(t, {
      id: 0,
      timestamp: "",
      event_type: eventType,
      actor: "",
      resource_kind: null,
      resource_name: null,
      details: null,
      trace_id: null,
      conversation_id: null,
      turn_id: null,
    })
      .toLowerCase()
      .includes(needle),
  );
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

/** The logger that emitted a record, if the line named one. */
export function daemonLogger(rec: DaemonLogRecord): string {
  const logger = rec.record?.logger;
  return typeof logger === "string" ? logger : "";
}

/**
 * The lines the daemon folded into this record — a traceback's frames, a
 * wrapped message — which belong to it rather than to a row each.
 */
export function daemonContinuation(rec: DaemonLogRecord): string[] {
  const lines = rec.record?.continuation;
  return Array.isArray(lines) ? lines.filter((l): l is string => typeof l === "string") : [];
}
