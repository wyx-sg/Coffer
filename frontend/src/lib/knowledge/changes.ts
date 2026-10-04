// frontend/src/lib/knowledge/changes.ts
//
// How the Knowledge page words and groups CHANGES — commits in the vault's
// history, each naming its writer (spec knowledge "Keep every document's
// history"). Pure functions over the wire shape, so
// the timeline, the change page and a document's History tab say the same
// thing about the same change and are unit-tested without a component.
//
// The daemon's own `summary` is a commit subject in English; the page words a
// change from its structured fields instead (writer, operation, agent, the
// documents it touched) and falls back to the summary only for an operation it
// has no words for — a change an earlier curation pass made reads as its
// summary, under the writer's curation label.
import type { TFunction } from "i18next";

import { agentTypeLabel } from "@/lib/agents/display";
import { timeAgo } from "@/lib/timeAgo";
import type { ChangeOut } from "@/lib/api/knowledge";
import { pathInCollection } from "@/lib/knowledge/routes";

/** Operations the page has words for (`knowledge.changes.op.<operation>`). */
const WORDED_OPERATIONS = new Set([
  "save",
  "delete",
  "promote",
  "restore",
  "edit",
  "sync",
  "create",
  "rename",
  "remove",
  "baseline",
]);

/** An agent as the page names it: an agent's resource name or type
 *  (`claude-code`, `claude_code`) as its product name, and `user` as you. */
export function agentLabel(t: TFunction, raw: string | null | undefined): string {
  if (!raw || raw === "agent") return t("knowledge.writer.agent");
  if (raw === "user" || raw === "ui") return t("knowledge.writer.user");
  return agentTypeLabel(raw.replace(/-/g, "_"));
}

/** Who wrote a change, in a word. */
export function writerLabel(t: TFunction, change: ChangeOut): string {
  switch (change.writer) {
    case "user":
      return t("knowledge.writer.user");
    case "agent":
      return agentLabel(t, change.agent);
    case "curation":
      return t("knowledge.writer.curation");
    case "sync":
      return t("knowledge.writer.sync");
    default:
      return t("knowledge.writer.disk");
  }
}

/** One sentence for what a change did, e.g. "Codex added daemon/port.md". */
export function changeSentence(t: TFunction, change: ChangeOut): string {
  if (!WORDED_OPERATIONS.has(change.operation)) return change.summary;
  const first = change.documents[0];
  return t(`knowledge.changes.op.${change.operation}`, {
    agent: agentLabel(t, change.agent),
    document: first ? pathInCollection(first.path) : "",
    count: change.documents.length,
  });
}

/** What a version did to the one document whose History lists it, e.g.
 *  "Saved by Codex", "Edited in Coffer" (board 5.1.03). */
export function versionSentence(t: TFunction, change: ChangeOut): string {
  if (!WORDED_OPERATIONS.has(change.operation)) return change.summary;
  return t(`knowledge.changes.version.${change.operation}`, {
    agent: agentLabel(t, change.agent),
  });
}

/** Operations whose timeline row names no document: they are about the
 *  collection. */
const COLLECTION_OPERATIONS = new Set(["create", "baseline", "remove"]);

/** Whether a restore brought back a whole collection: it put back the
 *  collection's own README, which only a deleted collection loses. */
function isCollectionRestore(change: ChangeOut): boolean {
  const name = change.collections[0];
  return (
    change.operation === "restore" &&
    Boolean(name) &&
    change.documents.some((d) => d.path === `${name}/README.md`)
  );
}

/** A timeline row's words (board 5.1.07): the verb after the writer's name,
 *  and the document it links to — "saved" ·
 *  `daemon/port.md` — or, for a change about a whole collection (deleted,
 *  restored), the collection instead. `more` counts the other documents a
 *  change touched. */
export function feedWords(
  t: TFunction,
  change: ChangeOut,
): { verb: string; document: string | null; collection: string | null; more: number } {
  const whole = change.operation === "remove" || isCollectionRestore(change);
  const verb = isCollectionRestore(change)
    ? t("knowledge.changes.verb.restoreCollection")
    : WORDED_OPERATIONS.has(change.operation)
      ? t(`knowledge.changes.verb.${change.operation}`, { agent: agentLabel(t, change.agent) })
      : change.summary;
  if (whole) {
    return { verb, document: null, collection: change.collections[0] ?? null, more: 0 };
  }
  if (COLLECTION_OPERATIONS.has(change.operation) || change.documents.length === 0) {
    return { verb, document: null, collection: null, more: 0 };
  }
  return {
    verb,
    document: change.documents[0].path,
    collection: null,
    more: change.documents.length - 1,
  };
}

/** The Author filter's "no filter" value. */
export const ANY_AUTHOR = "any";

/** Who a change is by, as a filter value: `user`, `curation`, `sync`, `disk`,
 *  or `agent:<name>` for an agent's own write (its resource name, so two agents
 *  never merge). */
export function authorKey(change: ChangeOut): string {
  return change.writer === "agent" ? `agent:${change.agent ?? "agent"}` : change.writer;
}

/** Whether a change passes the Author filter. */
export function matchesAuthor(change: ChangeOut, author: string): boolean {
  return author === ANY_AUTHOR || authorKey(change) === author;
}

/** The Author pill's choices, from the changes themselves: You first, then each
 *  agent by name, then Curation, Sync and disk edits — only those that appear. */
export function authorOptions(
  t: TFunction,
  changes: ChangeOut[],
): { value: string; label: string }[] {
  const seen = new Map<string, string>();
  for (const c of changes) {
    const key = authorKey(c);
    if (!seen.has(key)) seen.set(key, writerLabel(t, c));
  }
  const rank = (key: string) =>
    key === "user" ? 0 : key.startsWith("agent:") ? 1 : key === "curation" ? 2 : 3;
  return [...seen.entries()]
    .sort(([ka, la], [kb, lb]) => rank(ka) - rank(kb) || la.localeCompare(lb))
    .map(([value, label]) => ({ value, label }));
}

/** Whether `iso` falls within the last `days` days of `now`. */
export function withinDays(iso: string, days: number, now = Date.now()): boolean {
  const at = new Date(iso).getTime();
  return !Number.isNaN(at) && now - at <= days * 86_400_000;
}

/** The day heading a change sits under: "today", "yesterday", or the local
 *  date (YYYY-MM-DD). */
export function dayKey(iso: string, now = new Date()): string {
  const d = new Date(iso);
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((startOf(now) - startOf(d)) / 86_400_000);
  if (diff === 0) return "today";
  if (diff === 1) return "yesterday";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** Changes grouped under their day, keeping the timeline's newest-first order. */
export function groupByDay(changes: ChangeOut[], now = new Date()): [string, ChangeOut[]][] {
  const groups = new Map<string, ChangeOut[]>();
  for (const change of changes) {
    const key = dayKey(change.time, now);
    const list = groups.get(key) ?? [];
    list.push(change);
    groups.set(key, list);
  }
  return [...groups.entries()];
}

/** A change's time as the boards write it (5.1.03): "Today 12:04",
 *  "Yesterday 18:40", or "26 Sep 10:12" further back. */
export function whenLabel(t: TFunction, iso: string, locale: string, now = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const time = d.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", hour12: false });
  const day = dayKey(iso, now);
  if (day === "today") return t("knowledge.when.today", { time });
  if (day === "yesterday") return t("knowledge.when.yesterday", { time });
  const date = d.toLocaleDateString(locale, { day: "numeric", month: "short" });
  return `${date} ${time}`;
}

/** A timeline row's time (5.1.07): relative within today ("2 hours ago"),
 *  the day and the clock before that. */
export function feedTime(t: TFunction, iso: string, locale: string, now = new Date()): string {
  if (dayKey(iso, now) !== "today") return whenLabel(t, iso, locale, now);
  return timeAgo(iso, locale, now.getTime());
}

/** Whether a change removed something a person can put back from Recent
 *  changes — a deleted document or a deleted collection (spec knowledge
 *  "Restore a deleted collection or document from Recent changes"). */
export function isRestorableDelete(change: ChangeOut): boolean {
  return (
    (change.operation === "delete" || change.operation === "remove") &&
    change.documents.some((d) => d.status === "removed")
  );
}

/** The deletes a later change has already put back — the version each
 *  restore names. */
export function restoredVersions(changes: ChangeOut[]): Set<string> {
  return new Set(
    changes
      .filter((c) => c.operation === "restore")
      .map((c) => c.restored_from)
      .filter((v): v is string => Boolean(v)),
  );
}
