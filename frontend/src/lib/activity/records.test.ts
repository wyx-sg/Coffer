// src/lib/activity/records.test.ts — the one row shape over three logs, and the client-side half of Activity's filters.
import { describe, expect, test } from "vitest";
import type { TFunction } from "i18next";

import i18next from "@/i18n";
import {
  fromAudit,
  fromCall,
  fromDaemonTail,
  mergeNewestFirst,
  recordSeverity,
  formatDuration,
  type AuditEntry,
  type DaemonLogRecord,
  type Invocation,
} from "./records";
import {
  DEFAULT_FILTERS,
  filtersNarrow,
  matchesFilters,
  changeCategory,
  sourcesFor,
  type ActivityFilters,
  type FilterContext,
} from "./filters";

const t = i18next.t.bind(i18next) as TFunction;

const ctx: FilterContext = {
  t,
  agentNames: new Map([["a-cc", "Claude Code"]]),
  serverNames: new Map([["u-gh", "github"]]),
};

function call(overrides: Partial<Invocation> = {}): Invocation {
  return {
    id: 1,
    timestamp: "2026-09-29T14:32:08Z",
    resource_uid: "u-gh",
    resource_name: "github",
    capability_type: "tool",
    capability_key: "search_code",
    duration_ms: 412,
    status: "ok",
    error_message: null,
    session_id: "s-1",
    agent_uid: "a-cc",
    trace_id: null,
    ...overrides,
  };
}

function audit(overrides: Partial<AuditEntry> & { id: number }): AuditEntry {
  return {
    timestamp: "2026-09-29T14:00:00Z",
    event_type: "resource_created",
    resource_kind: null,
    resource_name: null,
    actor: "ui",
    details: null,
    trace_id: null,
    conversation_id: null,
    turn_id: null,
    ...overrides,
  };
}

const f = (patch: Partial<ActivityFilters>): ActivityFilters => ({ ...DEFAULT_FILTERS, ...patch });

describe("fromDaemonTail", () => {
  const line = (patch: Partial<DaemonLogRecord>): DaemonLogRecord => ({
    timestamp: null,
    level: null,
    event: null,
    offset: 0,
    record: {},
    ...patch,
  });

  test("an undated line borrows the time of the record it belongs to", () => {
    const rows = fromDaemonTail([
      line({ offset: 40, record: { raw: "Traceback" } }),
      line({ offset: 0, timestamp: "2026-09-29T14:00:00Z", level: "error", event: "boom" }),
    ]);
    expect(rows[0].at).toBe("2026-09-29T14:00:00Z");
  });

  test("a line with nothing to borrow keeps no time", () => {
    expect(fromDaemonTail([line({ record: { raw: "x" } })])[0].at).toBeNull();
  });

  test("a line's key is where it starts in the file: the same on every read and page", () => {
    const same = { timestamp: "2026-09-29T14:00:00Z", event: "tick" };
    const first = fromDaemonTail([line({ ...same, offset: 100 }), line({ ...same, offset: 50 })]);
    // A new line at the head, and the page boundary falling elsewhere.
    const second = fromDaemonTail([line({ ...same, offset: 150 }), line({ ...same, offset: 100 })]);
    expect(first.map((r) => r.key)).toEqual(["daemon:100", "daemon:50"]);
    expect(second[1].key).toBe(first[0].key);
    expect(new Set(first.map((r) => r.key)).size).toBe(2);
  });
});

test("mergeNewestFirst orders every log by time and drops duplicates", () => {
  const a = fromCall(call({ id: 1, timestamp: "2026-09-29T14:00:00Z" }));
  const b = fromCall(call({ id: 2, timestamp: "2026-09-29T14:02:00Z" }));
  const c = fromAudit(audit({ id: 9, timestamp: "2026-09-29T14:01:00Z" }));
  expect(mergeNewestFirst([[a], [b, c], [a]]).map((r) => r.key)).toEqual([b.key, c.key, a.key]);
});

describe("sourcesFor", () => {
  test("everything reads all three logs", () => {
    expect(sourcesFor("everything", DEFAULT_FILTERS)).toEqual(["change", "call", "daemon"]);
  });
  test("the kinds narrow everything to the logs they name", () => {
    expect(sourcesFor("everything", f({ kinds: ["calls"] }))).toEqual(["call"]);
    expect(sourcesFor("everything", f({ kinds: ["change:skill"] }))).toEqual(["change"]);
    expect(sourcesFor("everything", f({ kinds: ["calls", "changes"] }))).toEqual([
      "change",
      "call",
    ]);
  });
  test("a server or only agents leave the daemon log out", () => {
    expect(sourcesFor("everything", f({ server: "u-gh" }))).toEqual(["change", "call"]);
    expect(sourcesFor("everything", f({ by: ["agent:a-cc", "agent:a-cx"] }))).toEqual([
      "change",
      "call",
    ]);
  });
  test("a non-agent who keeps changes, and Coffer keeps its daemon records", () => {
    expect(sourcesFor("everything", f({ by: ["actor:you"] }))).toEqual(["change"]);
    expect(sourcesFor("everything", f({ by: ["actor:system"] }))).toEqual(["change", "daemon"]);
  });
});

describe("matchesFilters", () => {
  test("free text is the routes' job, not this predicate's", () => {
    const r = fromCall(call());
    expect(matchesFilters(r, "mcp", f({ search: "linear" }), ctx)).toBe(true);
  });

  test("an agent filter keeps that agent's calls and the changes it made", () => {
    const mine = fromCall(call());
    const theirs = fromCall(call({ id: 2, agent_uid: "a-codex" }));
    const change = fromAudit(
      audit({ id: 3, event_type: "knowledge_written", actor: "Claude Code" }),
    );
    const filters = f({ by: ["agent:a-cc"] });
    expect(matchesFilters(mine, "everything", filters, ctx)).toBe(true);
    expect(matchesFilters(theirs, "everything", filters, ctx)).toBe(false);
    expect(matchesFilters(change, "everything", filters, ctx)).toBe(true);
  });

  test("several who values keep a record that matches any of them", () => {
    const filters = f({ by: ["agent:a-cc", "actor:you"] });
    const byUi = fromAudit(audit({ id: 6, actor: "ui" }));
    const byDesktop = fromAudit(audit({ id: 7, actor: "desktop" }));
    const byCli = fromAudit(audit({ id: 8, actor: "cli" }));
    expect(matchesFilters(fromCall(call()), "everything", filters, ctx)).toBe(true);
    expect(matchesFilters(byUi, "everything", filters, ctx)).toBe(true);
    expect(matchesFilters(byDesktop, "everything", filters, ctx)).toBe(true);
    expect(matchesFilters(byCli, "everything", filters, ctx)).toBe(false);
  });

  test("a change kind with no resource is found by its event's area", () => {
    const secret = fromAudit(audit({ id: 9, event_type: "secret_set" }));
    const token = fromAudit(audit({ id: 10, event_type: "token_rotated" }));
    const skill = fromAudit(audit({ id: 11, resource_kind: "skill", resource_name: "pdf" }));
    expect(changeCategory(audit({ id: 0, event_type: "master_key_exported" }))).toBe("secret");
    expect(changeCategory(audit({ id: 0, event_type: "sync_run" }))).toBe("sync");
    const filters = f({ kinds: ["change:secret", "change:settings"] });
    expect(matchesFilters(secret, "everything", filters, ctx)).toBe(true);
    expect(matchesFilters(token, "everything", filters, ctx)).toBe(true);
    expect(matchesFilters(skill, "everything", filters, ctx)).toBe(false);
    expect(matchesFilters(skill, "everything", f({ kinds: ["changes"] }), ctx)).toBe(true);
    expect(matchesFilters(fromCall(call()), "everything", filters, ctx)).toBe(false);
  });

  test("a server filter keeps changes to that server", () => {
    const base = { event_type: "resource_updated", resource_kind: "mcp_server" };
    const edit = fromAudit(audit({ ...base, id: 4, resource_name: "github" }));
    const other = fromAudit(audit({ ...base, id: 5, resource_name: "linear" }));
    expect(matchesFilters(edit, "everything", f({ server: "u-gh" }), ctx)).toBe(true);
    expect(matchesFilters(other, "everything", f({ server: "u-gh" }), ctx)).toBe(false);
  });

  test("the custom range's upper bound is applied here", () => {
    const r = fromCall(call({ timestamp: "2026-09-29T15:00:00Z" }));
    expect(
      matchesFilters(r, "mcp", DEFAULT_FILTERS, { ...ctx, until: "2026-09-29T14:59:00Z" }),
    ).toBe(false);
  });
});

test("filtersNarrow ignores filters a tab does not show", () => {
  expect(filtersNarrow(f({ status: "error" }), "everything")).toBe(false);
  expect(filtersNarrow(f({ status: "error" }), "mcp")).toBe(true);
  expect(filtersNarrow(DEFAULT_FILTERS, "daemon")).toBe(false);
});

test("severity and duration read the way a person reads them", () => {
  expect(recordSeverity(fromCall(call({ status: "error" })))).toBe("error");
  expect(recordSeverity(fromCall(call({ status: "timeout" })))).toBe("warning");
  expect(formatDuration(12)).toBe("12 ms");
  expect(formatDuration(1300)).toBe("1.3 s");
});
