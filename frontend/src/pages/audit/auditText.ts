import type { TFunction } from "i18next";
import type { components } from "@/lib/api/types";

type AuditEntry = components["schemas"]["AuditEntryOut"];

/**
 * Render one audit entry as a plain-language activity sentence — the same
 * text the table row shows. Shared by the audit DataTable column (display)
 * and the audit-log search box (the haystack to match a query against), so
 * the two never drift apart.
 */
export function describeActivity(t: TFunction, entry: AuditEntry): string {
  const details = (entry.details ?? {}) as Record<string, unknown>;
  const capTypeRaw = typeof details.capability_type === "string" ? details.capability_type : "";
  return t(`audit.activity.${entry.event_type}`, {
    defaultValue: entry.event_type,
    resource: entry.resource_name ?? "",
    key: typeof details.key === "string" ? details.key : "",
    capType: capTypeRaw ? t(`audit.capType.${capTypeRaw}`, { defaultValue: capTypeRaw }) : "",
  });
}

/**
 * The lowercased free-text haystack for one entry — everything a user
 * might type into the search box (the activity sentence, resource name,
 * raw event code, and the humanised actor).
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
