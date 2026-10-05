// frontend/src/lib/knowledge/changes.ts
//
// How a knowledge writer and a change's time are worded: an agent by its
// product name, a writer in a word, a time as the boards write it. Pure
// functions over the wire shape, unit-tested without a component. The Knowledge
// page shows no timeline of changes (spec knowledge "Follow edits across
// collections in one feed" — the feed is only read to undo a delete), so this
// is what remains of that wording.
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
    default:
      return t("knowledge.writer.disk");
  }
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
