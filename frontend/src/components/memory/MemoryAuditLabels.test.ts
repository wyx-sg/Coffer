// frontend/src/components/memory/MemoryAuditLabels.test.ts
//
// The memory layer has no audit surface of its own: its events are read on
// the vault-wide Activity page, through `describeActivity`. Every event type
// the layer records must read there as a sentence in both interface
// languages, never as its raw event code. The event types come from the
// backend's own enum, dumped into `backend-keys.fixture.json`.
import { expect } from "vitest";
import type { TFunction } from "i18next";

import i18next from "@/i18n";
import backendKeys from "@/i18n/backend-keys.fixture.json";
import type { components } from "@/lib/api/types";
import { describeActivity } from "@/pages/activity/activityText";
import { acceptance } from "@/test/acceptance";

type AuditEntry = components["schemas"]["AuditEntryOut"];

const MEMORY_EVENTS = (backendKeys.auditEvents as string[]).filter((e) => e.startsWith("memory_"));

function entry(eventType: string): AuditEntry {
  return {
    id: 1,
    timestamp: "2026-09-01T12:00:00Z",
    actor: "api",
    resource_kind: "memory",
    resource_name: "coffer",
    details: null,
    event_type: eventType,
  } as AuditEntry;
}

acceptance("memory", "label every memory event type on the audit surface", () => {
  // Aggregation, distil, and delivery installed / removed / fired.
  expect(MEMORY_EVENTS).toEqual(
    expect.arrayContaining([
      "memory_aggregated",
      "memory_distilled",
      "memory_delivery_installed",
      "memory_delivery_removed",
      "memory_delivery_fired",
    ]),
  );

  for (const lng of ["en", "zh"]) {
    const t = i18next.getFixedT(lng) as TFunction;
    const labels = new Set<string>();
    for (const eventType of MEMORY_EVENTS) {
      const label = describeActivity(t, entry(eventType));
      expect(label, `${lng}:${eventType}`).not.toBe(eventType);
      expect(label, `${lng}:${eventType}`).not.toContain(eventType);
      expect(label.trim().length, `${lng}:${eventType}`).toBeGreaterThan(0);
      labels.add(label);
    }
    // Each event reads as its own sentence, not one catch-all label.
    expect(labels.size).toBe(MEMORY_EVENTS.length);
  }
  // The two languages really are two: the zh labels are not the en ones.
  const en = i18next.getFixedT("en") as TFunction;
  const zh = i18next.getFixedT("zh") as TFunction;
  for (const eventType of MEMORY_EVENTS) {
    expect(describeActivity(zh, entry(eventType))).not.toBe(describeActivity(en, entry(eventType)));
  }
});
