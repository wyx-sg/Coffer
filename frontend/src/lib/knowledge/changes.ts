// frontend/src/lib/knowledge/changes.ts
//
// How the Knowledge page words and groups CHANGES — commits in the vault's
// history, each naming its writer (spec knowledge "Keep every document's
// history and undo a pass as a whole"). Pure functions over the wire shape, so
// the timeline, the change page and a document's History tab say the same
// thing about the same change and are unit-tested without a component.
//
// The daemon's own `summary` is a commit subject in English; the page words a
// change from its structured fields instead (writer, operation, agent, the
// documents it touched) and falls back to the summary only for an operation it
// has no words for.
import type { TFunction } from "i18next";

import { agentTypeLabel } from "@/lib/agents/display";
import type { ChangeOut } from "@/lib/api/knowledge";
import { pathInCollection } from "@/lib/knowledge/routes";

/** The timeline's writer filter: Everyone, Agents, You. */
export type WriterFilter = "everyone" | "agents" | "you";

/** Operations the page has words for (`knowledge.changes.op.<operation>`). */
const WORDED_OPERATIONS = new Set([
  "pass",
  "save",
  "delete",
  "promote",
  "submit",
  "restore",
  "undo",
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

/** One sentence for what a change did, e.g. "Curated Codex's item into
 *  daemon/port.md". */
export function changeSentence(t: TFunction, change: ChangeOut): string {
  if (!WORDED_OPERATIONS.has(change.operation)) return change.summary;
  const first = change.documents[0];
  return t(`knowledge.changes.op.${change.operation}`, {
    agent: agentLabel(t, change.agent),
    document: first ? pathInCollection(first.path) : "",
    count: change.documents.length,
  });
}

/** Whether a change passes the writer filter. A curation pass is the agents'
 *  (it curates what agents and uploads submitted); your own saves, restores
 *  and undos are yours. */
export function matchesWriter(change: ChangeOut, filter: WriterFilter): boolean {
  if (filter === "everyone") return true;
  const agents = change.writer === "agent" || change.writer === "curation";
  return filter === "agents" ? agents : change.writer === "user";
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

/** A pass that a later change has undone — the version the undo names. */
export function undoneVersions(changes: ChangeOut[]): Set<string> {
  return new Set(changes.map((c) => c.undoes).filter((v): v is string => Boolean(v)));
}
