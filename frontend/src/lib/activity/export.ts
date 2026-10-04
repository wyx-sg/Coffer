// src/lib/activity/export.ts — "Export filtered records…": every record of the visible tab that matches its filters, as JSON or CSV.
//
// The export is not a dump of what happens to be loaded: it pages each log
// the tab reads through its own route with the same server-side filters (the free text included),
// applies the same client-side predicate the list applies, and writes
// exactly those records (spec web-ui "Export the filtered Activity records
// from the header"). A cap keeps a runaway log from freezing the tab.
import {
  fetchAuditPage,
  fetchCallPage,
  fetchDaemonPage,
  MAX_PAGE,
  type SourceParams,
} from "@/lib/api/activity";
import {
  callServerLabel,
  daemonLevel,
  fromAudit,
  fromCall,
  fromDaemonTail,
  mergeNewestFirst,
  recordLogger,
  type ActivityRecord,
} from "./records";

/** The most records one export writes. */
const EXPORT_CAP = 10_000;

async function readAll(spec: SourceParams): Promise<ActivityRecord[]> {
  const out: ActivityRecord[] = [];
  let cursor: string | null = null;
  do {
    if (spec.source === "change") {
      const page = await fetchAuditPage(spec.params, MAX_PAGE, cursor);
      out.push(...page.entries.map(fromAudit));
      cursor = page.next_cursor;
    } else if (spec.source === "call") {
      const page = await fetchCallPage(spec.params, MAX_PAGE, cursor);
      out.push(...page.invocations.map(fromCall));
      cursor = page.next_cursor;
    } else {
      const page = await fetchDaemonPage(spec.params, MAX_PAGE, cursor);
      out.push(...fromDaemonTail(page.records));
      cursor = page.next_cursor ?? null;
    }
  } while (cursor && out.length < EXPORT_CAP);
  return out;
}

/** Every record the specs' routes hold that `keep` accepts, newest first, capped. */
export async function collectForExport(
  specs: readonly SourceParams[],
  keep: (r: ActivityRecord) => boolean,
): Promise<ActivityRecord[]> {
  const lists = await Promise.all(specs.map(readAll));
  return mergeNewestFirst(lists.map((list) => list.filter(keep))).slice(0, EXPORT_CAP);
}

/** The record as the daemon sent it, tagged with the log it came from. */
function rawOf(r: ActivityRecord): Record<string, unknown> {
  if (r.source === "change") return { source: "change", ...r.entry };
  // The hand-off prompt is for the drawer's button, not part of the record.
  if (r.source === "call") return { source: "mcp_call", ...r.call, handoff: undefined };
  return { source: "daemon_log", ...r.log, handoff: undefined };
}

export function toJson(records: readonly ActivityRecord[]): string {
  return `${JSON.stringify(records.map(rawOf), null, 2)}\n`;
}

const CSV_COLUMNS = [
  "time",
  "source",
  "event",
  "actor",
  "agent_uid",
  "server",
  "capability",
  "duration_ms",
  "status",
  "level",
  "logger",
  "message",
] as const;

function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function csvRow(r: ActivityRecord): Record<(typeof CSV_COLUMNS)[number], unknown> {
  const blank = {
    time: r.at,
    source: "",
    event: "",
    actor: "",
    agent_uid: "",
    server: "",
    capability: "",
    duration_ms: "",
    status: "",
    level: "",
    logger: "",
    message: "",
  };
  if (r.source === "change") {
    return {
      ...blank,
      source: "change",
      event: r.entry.event_type,
      actor: r.entry.actor,
      server: r.entry.resource_kind === "mcp_server" ? r.entry.resource_name : "",
      message: r.entry.resource_name ?? "",
    };
  }
  if (r.source === "call") {
    return {
      ...blank,
      source: "mcp_call",
      agent_uid: r.call.agent_uid,
      server: callServerLabel(r.call),
      capability: `${r.call.capability_type}:${r.call.capability_key}`,
      duration_ms: r.call.duration_ms,
      status: r.call.status,
      message: r.call.error_message,
    };
  }
  const raw = r.log.record?.raw;
  return {
    ...blank,
    source: "daemon_log",
    level: daemonLevel(r.log),
    logger: recordLogger(r),
    message: r.log.event ?? (typeof raw === "string" ? raw : ""),
  };
}

/** One row per record, a header first; values quoted where CSV needs it. */
export function toCsv(records: readonly ActivityRecord[]): string {
  const lines = [CSV_COLUMNS.join(",")];
  for (const r of records) {
    const row = csvRow(r);
    lines.push(CSV_COLUMNS.map((c) => csvCell(row[c])).join(","));
  }
  return `${lines.join("\r\n")}\r\n`;
}

/** Hand the viewer a file to save. */
export function saveFile(name: string, type: string, content: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoke on the next turn, after the click has started the download.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
