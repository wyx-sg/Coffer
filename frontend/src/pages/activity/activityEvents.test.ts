// frontend/src/pages/activity/activityEvents.test.ts
// Every audit event type the daemon can record reads as a plain-language line
// in both locales. The set comes from the checked-in fixture that `make lint`
// regenerates from the backend's AuditEventType and diffs, so an event added
// without a string fails CI rather than showing a reader `resource_enabled`.
import { expect } from "vitest";

import backendKeys from "@/i18n/backend-keys.fixture.json";
import i18n from "@/i18n";
import { acceptance } from "@/test/acceptance";
import { describeActivity } from "./activityText";
import type { components } from "@/lib/api/types";

type AuditEntry = components["schemas"]["AuditEntryOut"];

const entry = (event_type: string): AuditEntry =>
  ({
    id: 1,
    timestamp: "2026-05-28T12:00:00Z",
    event_type,
    resource_kind: "mcp_server",
    resource_name: "demo-fs",
    actor: "api",
    details: { capability_type: "tool", key: "readme" },
  }) as unknown as AuditEntry;

acceptance("web-ui", "every audit event type reads as a sentence in both locales", () => {
  const events: string[] = backendKeys.auditEvents;
  expect(events.length).toBeGreaterThan(0);
  expect(events).toContain("resource_enabled");

  for (const lang of ["en", "zh"]) {
    const t = i18n.getFixedT(lang);
    // Read the locale's own bundle, so a zh gap cannot hide behind the en fallback.
    const own = (i18n.getResourceBundle(lang, "translation") as { audit: { activity: object } })
      .audit.activity as Record<string, unknown>;
    for (const event of events) {
      expect(typeof own[event], `${lang}: ${event}`).toBe("string");
      const line = describeActivity(t, entry(event));
      expect(line.trim()).not.toBe("");
      expect(line).not.toBe(event);
      expect(line).not.toMatch(/\b[a-z]+_[a-z_]+\b/); // no raw snake_case code leaks through
    }
  }
  expect(describeActivity(i18n.getFixedT("en"), entry("resource_enabled"))).toBe("Enabled demo-fs");
});
