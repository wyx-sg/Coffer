// src/lib/overview/attention.test.ts — the Needs-you order and the page each row leads to.
import { describe, expect, test } from "vitest";

import type { AttentionItem } from "@/lib/hooks/useAttention";
import { actionLabelKey, actionPage, itemPage, severityTone, sortAttention } from "./attention";

function item(over: Partial<AttentionItem>): AttentionItem {
  return {
    kind: "mcp_server",
    uid: "u1",
    title: "github",
    reason_code: "mcp_failing",
    reason: "Its last connection test failed.",
    severity: "error",
    since: null,
    action: { verb: "test", method: "POST", path: "/api/v1/x", body: null },
    ...over,
  } as AttentionItem;
}

describe("sortAttention", () => {
  test("most severe first, then oldest first, undated last", () => {
    const sorted = sortAttention([
      item({ title: "info", severity: "info", since: "2026-09-01T00:00:00Z" }),
      item({ title: "err-undated", severity: "error", since: null }),
      item({ title: "warn", severity: "warning", since: "2026-09-02T00:00:00Z" }),
      item({ title: "err-new", severity: "error", since: "2026-09-29T00:00:00Z" }),
      item({ title: "err-old", severity: "error", since: "2026-09-01T00:00:00Z" }),
    ]);
    expect(sorted.map((i) => i.title)).toEqual([
      "err-old",
      "err-new",
      "err-undated",
      "warn",
      "info",
    ]);
  });

  test("does not reorder the input", () => {
    const input = [item({ severity: "info" }), item({ severity: "error" })];
    sortAttention(input);
    expect(input[0].severity).toBe("info");
  });
});

describe("pages", () => {
  test("each kind opens its own page", () => {
    expect(itemPage(item({ kind: "agent", uid: "a1" }))).toBe("/agents/a1");
    expect(itemPage(item({ kind: "mcp_server", uid: "m1" }))).toBe("/mcp-servers/m1");
    expect(itemPage(item({ kind: "channel", uid: "c1" }))).toBe("/channels/c1");
    expect(itemPage(item({ kind: "skill", uid: "s1" }))).toBe("/skills/s1");
    expect(itemPage(item({ kind: "provider", uid: "p1" }))).toBe("/model-providers/p1");
    expect(itemPage(item({ kind: "sync", uid: null }))).toBe("/sync");
    expect(itemPage(item({ kind: "reconcile", uid: null }))).toBe("/activity?tab=daemon");
    expect(itemPage(item({ kind: "mystery" }))).toBe("/activity");
  });

  test("a kind without a uid opens its list", () => {
    expect(itemPage(item({ kind: "skill", uid: null }))).toBe("/skills");
  });

  test("a missing secret is added on the Secrets page, the name still opens the server", () => {
    const secret = item({ reason_code: "mcp_missing_secret", uid: "m1" });
    expect(actionPage(secret)).toBe("/secrets");
    expect(itemPage(secret)).toBe("/mcp-servers/m1");
  });
});

test("an action label comes from its verb, falling back to Open", () => {
  expect(actionLabelKey("test")).toBe("overview.actions.test");
  expect(actionLabelKey("set_secret")).toBe("overview.actions.set_secret");
  expect(actionLabelKey("frobnicate")).toBe("overview.actions.open");
});

test("an error is red and anything else amber", () => {
  expect(severityTone("error")).toBe("err");
  expect(severityTone("warning")).toBe("warn");
  expect(severityTone("info")).toBe("warn");
});
