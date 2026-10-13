// frontend/src/lib/activity/activityText.ts
//
// Every plain-language line the Activity tabs render, and the search haystack
// that must match it. The two are deliberately produced by the same functions:
// the old audit page split them once and the search box promptly stopped
// matching what the row actually said.
import type { TFunction } from "i18next";
import type { components } from "@/lib/api/types";

import { agentLabel } from "./auditFacts";
import { auditVariant } from "./auditSentence";

type AuditEntry = components["schemas"]["AuditEntryOut"];
type DaemonLogRecord = components["schemas"]["DaemonLogRecordOut"];

/**
 * Render one audit entry as a plain-language activity sentence — the same
 * text the Changes row shows. The sentence names what the row acted on from
 * its `details` (see `auditSentence.ts`): a variant the row's fields fill
 * completely, else the event's plain sentence. Event types are translated per
 * locale (guarded by `i18n/backend-keys.test.ts`) so a zh reader never sees a
 * raw `resource_enabled` on a row.
 */
export function describeActivity(
  t: TFunction,
  entry: AuditEntry,
  secretLabels?: ReadonlyMap<string, string | null>,
): string {
  const details = (entry.details ?? {}) as Record<string, unknown>;
  const resource = entry.resource_name ?? "";
  const text = (k: string) => (typeof details[k] === "string" ? (details[k] as string) : "");
  const base = {
    defaultValue: entry.event_type,
    resource,
    command: text("command"),
    // The agent a skill was bound to or unbound from (`details.agent`, written
    // by the link reconciler); older rows carry none.
    agent: text("agent") ? agentLabel(text("agent")) : t("audit.agentFallback"),
  };
  const plain = t(`audit.activity.${entry.event_type}`, base);
  const variant = auditVariant(entry.event_type, details, { t, resource, secretLabels });
  if (!variant) return plain;
  return t(`audit.activity.${entry.event_type}_${variant.v}`, {
    ...base,
    ...variant.p,
    defaultValue: plain,
  });
}

/** Where the event sentences and their variants live. */
const ACTIVITY_KEYS = "audit.activity";

/** The `audit.activity` strings in `t`'s language. */
function activityBundle(t: TFunction): Record<string, unknown> {
  const bundle: unknown = t(ACTIVITY_KEYS, { returnObjects: true });
  return bundle !== null && typeof bundle === "object" ? (bundle as Record<string, unknown>) : {};
}

/**
 * Every audit event type the current locale words as a sentence. A key that
 * extends another key (`secret_set_replaced` of `secret_set`) is one of that
 * event's variants, not an event: no event's name extends another's.
 */
function knownEventTypes(keys: readonly string[]): string[] {
  return keys.filter((k) => !keys.some((other) => other !== k && k.startsWith(`${other}_`)));
}

/** A variant's wording with its blanks left out, for the search to match. */
const withoutBlanks = (template: unknown) =>
  typeof template === "string" ? template.replace(/\{\{[^}]*\}\}/g, "") : "";

/**
 * The audit event types whose sentence, in the reader's language, contains
 * `text`. The sentence a row shows is composed here from the event type and
 * its details, so the database cannot search it; it searches the raw event
 * code, the resource, the actor and the details itself, and is told these
 * event types in addition (`q_type`). An event matches on its plain sentence
 * or on the fixed words of any of its variants.
 */
export function eventTypesMatching(t: TFunction, text: string): string[] {
  const needle = text.trim().toLowerCase();
  if (!needle) return [];
  const bundle = activityBundle(t);
  const keys = Object.keys(bundle);
  return knownEventTypes(keys).filter((eventType) => {
    const plain = describeActivity(t, {
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
    });
    const variants = keys
      .filter((k) => k.startsWith(`${eventType}_`))
      .map((k) => withoutBlanks(bundle[k]));
    return [plain, ...variants].some((s) => s.toLowerCase().includes(needle));
  });
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
