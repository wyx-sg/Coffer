// src/lib/activity/recordText.test.ts — where a change's "Open X" leads, and who a record names.
import type { TFunction } from "i18next";
import { describe, expect, test } from "vitest";

import i18next from "@/i18n";

import type { AuditEntry } from "./records";
import { actorLabel, actorLong, changeLink } from "./recordText";

function entry(resource_kind: string, resource_name: string): AuditEntry {
  return {
    id: 1,
    actor: "user",
    conversation_id: null,
    details: null,
    event_type: "resource_updated",
    resource_kind,
    resource_name,
    timestamp: "2026-10-04T09:41:17Z",
    trace_id: null,
    turn_id: null,
  };
}

describe("changeLink", () => {
  test("an agent opens its own page, addressed by type", () => {
    expect(changeLink(entry("agent", "claude-code"))).toEqual({
      to: "/agents/claude_code",
      name: "claude-code",
    });
    expect(changeLink(entry("agent", "codex"))?.to).toBe("/agents/codex");
  });

  test("a uid-addressed kind opens its detail page once the uid is known", () => {
    expect(changeLink(entry("provider", "agnes"), "p-1")?.to).toBe("/model-providers/p-1");
    expect(changeLink(entry("channel", "seatalk"), "c-1")?.to).toBe("/channels/c-1");
    expect(changeLink(entry("knowledge", "shopee"), "k-1")?.to).toBe("/knowledge/k-1");
    // Not found (deleted since): the kind's list.
    expect(changeLink(entry("knowledge", "gone"))?.to).toBe("/knowledge");
  });

  test("an old memory partition's record keeps its label but opens nothing", () => {
    // Memory partitions are gone; their past records stay readable, unlinked.
    expect(changeLink(entry("memory", "coffer"), "m-1")).toBeNull();
  });

  test("a name-addressed kind opens by name", () => {
    expect(changeLink(entry("mcp_server", "github"))?.to).toBe("/mcp-servers/github");
    expect(changeLink(entry("skill", "pdf"))?.to).toBe("/skills/pdf");
  });
});

describe("actorLabel / actorLong", () => {
  const en = i18next.getFixedT("en") as TFunction;
  const zh = i18next.getFixedT("zh") as TFunction;

  test("Coffer itself reads as Coffer, whichever way it recorded itself", () => {
    for (const actor of ["coffer", "system", "system:memory-sync-worker", "system:upgrade"]) {
      expect(actorLabel(en, actor)).toBe("Coffer");
      expect(actorLong(en, actor)).toBe("Coffer");
      expect(actorLabel(zh, actor)).toBe("Coffer");
    }
  });

  test("a person reads as You, with where they acted", () => {
    expect(actorLabel(en, "ui")).toBe("You · web UI");
    expect(actorLabel(en, "desktop")).toBe("You · Coffer app");
    expect(actorLabel(en, "cli")).toBe("You · command line");
    expect(actorLabel(en, "user")).toBe("You");
    expect(actorLabel(en, "human")).toBe("Outside Coffer");
    expect(actorLabel(en, "api")).toBe("API");
    expect(actorLabel(en, "sync")).toBe("Sync");
    expect(actorLabel(zh, "cli")).toBe("你 · 命令行");
    expect(actorLong(en, "desktop")).toBe("You, in the Coffer app");
  });

  test("an actor Coffer has no word for reads as recorded", () => {
    expect(actorLabel(en, "e2e-mcp")).toBe("e2e-mcp");
    expect(actorLong(en, "e2e-mcp")).toBe("e2e-mcp");
  });
});
