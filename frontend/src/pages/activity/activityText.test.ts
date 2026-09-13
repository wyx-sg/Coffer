// frontend/src/pages/activity/activityText.test.ts
import { describe, expect, test } from "vitest";
import i18next from "@/i18n";
import type { TFunction } from "i18next";
import type { components } from "@/lib/api/types";
import {
  auditSearchHaystack,
  daemonLogger,
  daemonSearchHaystack,
  describeActivity,
  describeDaemonRecord,
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
    ...overrides,
  };
}

describe("describeActivity", () => {
  test("resource_created → 'Registered <name>'", () => {
    expect(
      describeActivity(
        t,
        makeEntry({ event_type: "resource_created", resource_name: "filesystem" }),
      ),
    ).toBe("Registered filesystem");
  });

  test("resource_updated → 'Reconfigured <name>'", () => {
    expect(
      describeActivity(t, makeEntry({ event_type: "resource_updated", resource_name: "github" })),
    ).toBe("Reconfigured github");
  });

  test("resource_enabled → 'Enabled <name>'", () => {
    expect(
      describeActivity(t, makeEntry({ event_type: "resource_enabled", resource_name: "fs" })),
    ).toBe("Enabled fs");
  });

  test("resource_disabled → 'Disabled <name>'", () => {
    expect(
      describeActivity(t, makeEntry({ event_type: "resource_disabled", resource_name: "fs" })),
    ).toBe("Disabled fs");
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
        record: { raw: "Traceback (most recent call last):" },
      }),
    ).toBe("Traceback (most recent call last):");
  });

  test("a record with neither still renders something readable", () => {
    const line = describeDaemonRecord(t, { timestamp: null, level: null, event: null, record: {} });
    expect(line).not.toBe("");
    expect(line).not.toContain("undefined");
  });
});

describe("auditSearchHaystack", () => {
  test("covers the rendered line, the resource, the raw event code and the actor", () => {
    const haystack = auditSearchHaystack(
      t,
      makeEntry({ event_type: "resource_created", resource_name: "Filesystem" }),
    );
    expect(haystack).toContain("registered filesystem");
    expect(haystack).toContain("resource_created");
    expect(haystack).toContain("api");
  });

  test("the haystack is always lowercase", () => {
    const haystack = auditSearchHaystack(
      t,
      makeEntry({ event_type: "resource_created", resource_name: "Filesystem" }),
    );
    expect(haystack).toBe(haystack.toLowerCase());
  });
});

describe("daemonLogger", () => {
  test("names the structlog logger, and is empty when the line carried none", () => {
    expect(
      daemonLogger({
        timestamp: null,
        level: null,
        event: null,
        record: { logger: "coffer.sync" },
      }),
    ).toBe("coffer.sync");
    expect(
      daemonLogger({ timestamp: null, level: null, event: null, record: { raw: "boom" } }),
    ).toBe("");
  });
});

describe("daemonSearchHaystack", () => {
  test("covers the message, the logger and the level", () => {
    const haystack = daemonSearchHaystack(t, {
      timestamp: "2026-05-22T12:00:00Z",
      level: "ERROR",
      event: "channel_send_failed",
      record: { event: "channel_send_failed", level: "ERROR", logger: "coffer.channels" },
    });
    expect(haystack).toContain("channel_send_failed");
    expect(haystack).toContain("coffer.channels");
    expect(haystack).toContain("error");
    expect(haystack).toBe(haystack.toLowerCase());
  });

  test("a line that was not JSON is searchable by its verbatim text", () => {
    const haystack = daemonSearchHaystack(t, {
      timestamp: null,
      level: null,
      event: null,
      record: { raw: "Traceback (most recent call last):" },
    });
    expect(haystack).toContain("traceback");
  });
});
