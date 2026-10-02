// frontend/src/lib/activity/activityText.test.ts
import { describe, expect, test } from "vitest";
import i18next from "@/i18n";
import type { TFunction } from "i18next";
import type { components } from "@/lib/api/types";
import {
  daemonLogger,
  describeActivity,
  describeDaemonRecord,
  eventTypesMatching,
} from "./activityText";

type AuditEntry = components["schemas"]["AuditEntryOut"];

const t = i18next.t.bind(i18next) as TFunction;

function makeEntry(overrides: Partial<AuditEntry> & { event_type: string }): AuditEntry {
  return {
    id: 1,
    timestamp: "2026-05-22T12:00:00Z",
    actor: "api",
    resource_kind: null,
    resource_name: null,
    details: null,
    trace_id: null,
    conversation_id: null,
    turn_id: null,
    ...overrides,
  };
}

describe("describeActivity", () => {
  test("resource_created → 'Added <name>'", () => {
    expect(
      describeActivity(
        t,
        makeEntry({ event_type: "resource_created", resource_name: "filesystem" }),
      ),
    ).toBe("Added filesystem");
  });

  test("resource_updated → 'Reconfigured <name>'", () => {
    expect(
      describeActivity(t, makeEntry({ event_type: "resource_updated", resource_name: "github" })),
    ).toBe("Reconfigured github");
  });

  test("resource_enabled → 'Turned on <name>'", () => {
    expect(
      describeActivity(t, makeEntry({ event_type: "resource_enabled", resource_name: "fs" })),
    ).toBe("Turned on fs");
  });

  test("resource_disabled → 'Turned off <name>'", () => {
    expect(
      describeActivity(t, makeEntry({ event_type: "resource_disabled", resource_name: "fs" })),
    ).toBe("Turned off fs");
  });

  test("resource_deleted → 'Removed <name>'", () => {
    expect(
      describeActivity(t, makeEntry({ event_type: "resource_deleted", resource_name: "old" })),
    ).toBe("Removed old");
  });

  test("capability_enabled → includes cap type and key", () => {
    const result = describeActivity(
      t,
      makeEntry({
        event_type: "capability_enabled",
        resource_name: "fs",
        details: { capability_type: "tool", key: "read_file" },
      }),
    );
    expect(result).toContain("read_file");
    expect(result).toContain("fs");
  });

  test("capability_enabled on a resource capability keeps the key verbatim", () => {
    const result = describeActivity(
      t,
      makeEntry({
        event_type: "capability_enabled",
        resource_name: "fs",
        details: { capability_type: "resource", key: "file://path" },
      }),
    );
    expect(result).toContain("file://path");
  });

  test("capability_disabled → includes cap type and key", () => {
    const result = describeActivity(
      t,
      makeEntry({
        event_type: "capability_disabled",
        resource_name: "fs",
        details: { capability_type: "prompt", key: "my-prompt" },
      }),
    );
    expect(result).toContain("my-prompt");
  });

  test("token_rotated → 'Access token rotated'", () => {
    expect(describeActivity(t, makeEntry({ event_type: "token_rotated" }))).toBe(
      "Access token rotated",
    );
  });

  test("retention_updated → 'Updated a data-retention policy'", () => {
    expect(describeActivity(t, makeEntry({ event_type: "retention_updated" }))).toBe(
      "Updated a data-retention policy",
    );
  });

  test("skill_bound / skill_unbound name the agent the skill was bound to or unbound from", () => {
    const details = { agent: "claude_code" };
    expect(
      describeActivity(
        t,
        makeEntry({ event_type: "skill_bound", resource_name: "demo-cli", details }),
      ),
    ).toBe("Bound skill demo-cli to Claude Code");
    expect(
      describeActivity(
        t,
        makeEntry({ event_type: "skill_unbound", resource_name: "demo-cli", details }),
      ),
    ).toBe("Unbound skill demo-cli from Claude Code");
  });

  test("a skill binding row written without an agent still reads as a sentence", () => {
    expect(
      describeActivity(t, makeEntry({ event_type: "skill_unbound", resource_name: "demo-cli" })),
    ).toBe("Unbound skill demo-cli from an agent");
  });

  test("unknown event_type falls back to the raw event code", () => {
    expect(describeActivity(t, makeEntry({ event_type: "totally_unknown_event_xyz" }))).toBe(
      "totally_unknown_event_xyz",
    );
  });
});

describe("describeDaemonRecord", () => {
  test("uses structlog's event field", () => {
    expect(
      describeDaemonRecord(t, {
        timestamp: "2026-05-22T12:00:00Z",
        level: "warning",
        event: "auto_sync_failed",
        offset: 0,
        record: { event: "auto_sync_failed" },
      }),
    ).toBe("auto_sync_failed");
  });

  test("falls back to the verbatim line when the record did not parse as JSON", () => {
    expect(
      describeDaemonRecord(t, {
        timestamp: null,
        level: null,
        event: null,
        offset: 0,
        record: { raw: "Traceback (most recent call last):" },
      }),
    ).toBe("Traceback (most recent call last):");
  });

  test("a record with neither still renders something readable", () => {
    const line = describeDaemonRecord(t, {
      timestamp: null,
      level: null,
      event: null,
      offset: 0,
      record: {},
    });
    expect(line).not.toBe("");
    expect(line).not.toContain("undefined");
  });
});

describe("eventTypesMatching", () => {
  test("finds the events whose sentence holds the text, in the reader's language", () => {
    expect(eventTypesMatching(t, "unbound")).toEqual(["skill_unbound"]);
    expect(eventTypesMatching(t, "UNBOUND skill")).toEqual(["skill_unbound"]);
    expect(eventTypesMatching(t, "")).toEqual([]);
    expect(eventTypesMatching(t, "no-event-says-this-xyz")).toEqual([]);
  });

  test("reads the other locale's wording when that is the reader's", async () => {
    const zh = i18next.getFixedT("zh") as TFunction;
    expect(eventTypesMatching(zh, "解绑")).toContain("skill_unbound");
  });
});

describe("daemonLogger", () => {
  test("names the structlog logger, and is empty when the line carried none", () => {
    expect(
      daemonLogger({
        timestamp: null,
        level: null,
        event: null,
        offset: 0,
        record: { logger: "coffer.sync" },
      }),
    ).toBe("coffer.sync");
    expect(
      daemonLogger({
        timestamp: null,
        level: null,
        event: null,
        offset: 0,
        record: { raw: "boom" },
      }),
    ).toBe("");
  });
});
