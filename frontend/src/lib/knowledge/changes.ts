// frontend/src/lib/knowledge/changes.ts
//
// How a knowledge writer, a change and its time are worded: an agent by its
// product name, a writer in a word, what a change did in a few words, a time as
// the boards write it. Pure functions over the wire shape, unit-tested without
// a component; a collection page's Change log reads them (spec knowledge "Show
// a collection as one tree of read-only documents in the web UI").
import type { TFunction } from "i18next";

import { agentTypeLabel } from "@/lib/agents/display";
import type { ChangeOut } from "@/lib/api/knowledge";

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
    case "daemon":
      return t("knowledge.writer.daemon");
    default:
      return t("knowledge.writer.disk");
  }
}

/** The operations a change can name, each worded under `knowledge.operation`. */
const OPERATIONS = new Set([
  "save",
  "delete",
  "promote",
  "restore",
  "edit",
  "sync",
  "create",
  "rename",
  "remove",
  "layout",
  "baseline",
]);

/** What a change did, in a few words; a retired curation pass's change
 *  (`pass`, `submit`, `undo`) reads as curation, anything else as its summary. */
export function operationLabel(t: TFunction, change: ChangeOut): string {
  if (OPERATIONS.has(change.operation)) return t(`knowledge.operation.${change.operation}`);
  if (["pass", "submit", "undo"].includes(change.operation)) {
    return t("knowledge.operation.curation");
  }
  return change.summary || change.operation;
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
