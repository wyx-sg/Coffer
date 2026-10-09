// src/lib/activity/recordText.test.ts — where a change's "Open X" leads: the resource's own detail page.
import { describe, expect, test } from "vitest";

import type { AuditEntry } from "./records";
import { changeLink } from "./recordText";

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
