// frontend/src/pages/audit/auditText.test.ts
import { describe, expect, test } from "vitest";
import i18next from "@/i18n";
import type { TFunction } from "i18next";
import type { components } from "@/lib/api/types";
import { describeActivity, auditSearchHaystack } from "./auditText";

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
    const entry = makeEntry({
      event_type: "resource_created",
      resource_name: "filesystem",
    });
    expect(describeActivity(t, entry)).toBe("Registered filesystem");
  });

  test("resource_updated → 'Reconfigured <name>'", () => {
    const entry = makeEntry({
      event_type: "resource_updated",
      resource_name: "github",
    });
    expect(describeActivity(t, entry)).toBe("Reconfigured github");
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
      describeActivity(
        t,
        makeEntry({ event_type: "resource_deleted", resource_name: "old-server" }),
      ),
    ).toBe("Removed old-server");
  });

  test("capability_first_seen → includes cap type and key", () => {
    const entry = makeEntry({
      event_type: "capability_first_seen",
      resource_name: "fs",
      details: { capability_type: "tool", key: "read_file" },
    });
    const result = describeActivity(t, entry);
    expect(result).toContain("read_file");
    expect(result).toContain("fs");
  });

  test("capability_enabled → includes cap type and key", () => {
    const entry = makeEntry({
      event_type: "capability_enabled",
      resource_name: "fs",
      details: { capability_type: "resource", key: "file://path" },
    });
    const result = describeActivity(t, entry);
    expect(result).toContain("file://path");
  });

  test("capability_disabled → includes cap type and key", () => {
    const entry = makeEntry({
      event_type: "capability_disabled",
      resource_name: "fs",
      details: { capability_type: "prompt", key: "my-prompt" },
    });
    const result = describeActivity(t, entry);
    expect(result).toContain("my-prompt");
  });

  test("daemon_started → 'Daemon started'", () => {
    expect(describeActivity(t, makeEntry({ event_type: "daemon_started" }))).toBe("Daemon started");
  });

  test("daemon_stopped → 'Daemon stopped'", () => {
    expect(describeActivity(t, makeEntry({ event_type: "daemon_stopped" }))).toBe("Daemon stopped");
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

  test("backup_created → 'Created a backup'", () => {
    expect(describeActivity(t, makeEntry({ event_type: "backup_created" }))).toBe(
      "Created a backup",
    );
  });

  test("unknown event_type falls back to the raw event code", () => {
    const result = describeActivity(t, makeEntry({ event_type: "totally_unknown_event_xyz" }));
    // i18next defaultValue is the event_type itself
    expect(result).toBe("totally_unknown_event_xyz");
  });
});

describe("auditSearchHaystack", () => {
  test("haystack is lowercased and includes the activity sentence, resource name, event code, and actor", () => {
    const entry = makeEntry({
      event_type: "resource_created",
      resource_name: "Filesystem",
      actor: "api",
    });
    const haystack = auditSearchHaystack(t, entry);
    expect(haystack).toContain("filesystem");
    expect(haystack).toContain("resource_created");
    // Actor "api" -> translated as "API" then lowercased
    expect(haystack).toContain("api");
  });

  test("haystack is always lowercase", () => {
    const entry = makeEntry({
      event_type: "resource_created",
      resource_name: "MyServer",
    });
    expect(auditSearchHaystack(t, entry)).toBe(auditSearchHaystack(t, entry).toLowerCase());
  });
});
