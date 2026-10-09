// src/lib/overview/attention.test.ts — the Needs-you order and the page each row leads to.
import { describe, expect, test } from "vitest";

import type { AttentionItem } from "@/lib/hooks/useAttention";
import {
  actionIcon,
  actionLabelKey,
  actionPage,
  inPlaceVerb,
  itemActionLabelKey,
  itemPage,
  opensApprovals,
  severityTone,
  sortAttention,
} from "./attention";

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
    expect(itemPage(item({ kind: "agent", uid: "a1" }), "claude_code")).toBe("/agents/claude_code");
    expect(itemPage(item({ kind: "mcp_server", uid: "m1", title: "github" }))).toBe(
      "/mcp-servers/github",
    );
    expect(itemPage(item({ kind: "channel", uid: "c1" }))).toBe("/channels/c1");
    expect(itemPage(item({ kind: "skill", uid: "s1", title: "code-review" }))).toBe(
      "/skills/code-review",
    );
    expect(itemPage(item({ kind: "provider", uid: "p1" }))).toBe("/model-providers/p1");
    expect(itemPage(item({ kind: "sync", uid: null }))).toBe("/sync");
    expect(itemPage(item({ kind: "reconcile", uid: null }))).toBe("/activity?tab=daemon");
    expect(itemPage(item({ kind: "mystery" }))).toBe("/activity");
  });

  test("a kind without a uid opens its list", () => {
    expect(itemPage(item({ kind: "skill", uid: null }))).toBe("/skills");
  });

  test("an agent whose type is not known yet opens the agent list", () => {
    expect(itemPage(item({ kind: "agent", uid: "a1" }))).toBe("/agents");
  });

  test("a missing secret is added on the Secrets page, the name still opens the server", () => {
    const secret = item({ reason_code: "mcp_missing_secret", uid: "m1" });
    expect(actionPage(secret)).toBe("/secrets");
    expect(itemPage(secret)).toBe("/mcp-servers/github");
  });

  test("a rejected key opens the server's page, where the key is replaced", () => {
    const rejected = item({ reason_code: "mcp_key_rejected", uid: "m1" });
    expect(actionPage(rejected)).toBe("/mcp-servers/github");
  });

  test("a secret a skill requires is set on the Secrets page, the name opens the skill", () => {
    const secret = item({
      kind: "skill",
      uid: "s1",
      title: "gh-triage",
      reason_code: "skill_missing_secret",
    });
    expect(actionPage(secret)).toBe("/secrets");
    expect(itemPage(secret)).toBe("/skills/gh-triage");
  });
});

test("an agent's repair opens the agent's page and reads by its verb", () => {
  const repair = item({
    kind: "agent",
    uid: "a1",
    reason_code: "agent_partial",
    action: { verb: "repair", method: "POST", path: "/api/v1/reconcile/apply", body: null },
  });
  expect(actionPage(repair, "claude_code")).toBe("/agents/claude_code");
  expect(itemActionLabelKey(repair)).toBe("overview.actions.repair");
  const drift = item({ ...repair, kind: "skill", uid: "s1", title: "code-review" });
  expect(actionPage(drift)).toBe("/skills/code-review");
});

test("an action label comes from its verb, falling back to Open", () => {
  expect(actionLabelKey("test")).toBe("overview.actions.test");
  expect(actionLabelKey("set_secret")).toBe("overview.actions.set_secret");
  expect(actionLabelKey("frobnicate")).toBe("overview.actions.open");
  expect(actionLabelKey("turn_on")).toBe("overview.actions.turn_on");
});

test("the secret-approval item opens Settings, Security tab", () => {
  const off = item({
    kind: "secret",
    uid: null,
    title: "Secret approval",
    reason_code: "secret_approval_off",
    action: {
      verb: "turn_on",
      method: "PUT",
      path: "/api/v1/settings/secret-boundary",
      body: { require_approval: true },
    },
  });
  expect(itemPage(off)).toBe("/settings/security");
  expect(actionPage(off)).toBe("/settings/security");
  expect(itemActionLabelKey(off)).toBe("overview.actions.turn_on");
});

test("the two Secrets-page signals lead to /secrets; Review on approvals opens the dialog", () => {
  const missing = item({
    kind: "secret",
    uid: "fp1",
    title: "Secrets",
    reason_code: "secret_missing_here",
    reason: "3 secrets have no value on this Mac.",
    action: { verb: "open", method: "GET", path: "/api/v1/secrets", body: null },
  });
  expect(itemPage(missing)).toBe("/secrets");
  expect(actionPage(missing)).toBe("/secrets");
  expect(itemActionLabelKey(missing)).toBe("overview.actions.openSecrets");
  expect(opensApprovals(missing)).toBe(false);

  const waiting = item({
    kind: "secret",
    uid: "fp2",
    title: "Secret approvals",
    reason_code: "secret_approvals_pending",
    severity: "warning",
    action: { verb: "review", method: "GET", path: "/api/v1/secrets/approvals", body: null },
  });
  // The name opens Secrets, where the banner is; the action opens the global dialog instead.
  expect(itemPage(waiting)).toBe("/secrets");
  expect(itemActionLabelKey(waiting)).toBe("overview.actions.review");
  expect(opensApprovals(waiting)).toBe(true);
});

test("an error is red and anything else amber", () => {
  expect(severityTone("error")).toBe("err");
  expect(severityTone("warning")).toBe("warn");
  expect(severityTone("info")).toBe("warn");
});

test("a channel's check and sync's review read by what they do", () => {
  const channel = item({
    kind: "channel",
    action: { verb: "check", method: "GET", path: "/x", body: null },
  });
  expect(itemActionLabelKey(channel)).toBe("overview.actions.reconnectChannel");
  const sync = item({
    kind: "sync",
    action: { verb: "review", method: "GET", path: "/x", body: null },
  });
  expect(itemActionLabelKey(sync)).toBe("overview.actions.reviewHeld");
  // Another kind's check keeps the plain verb.
  expect(itemActionLabelKey(item({ kind: "cli", action: channel.action }))).toBe(
    "overview.actions.check",
  );
});

test("every verb that has an icon names one, the others none", () => {
  for (const verb of [
    "set_secret",
    "replace_key",
    "review",
    "connect",
    "repair",
    "check",
    "test",
  ]) {
    expect(actionIcon(verb)).toBeDefined();
  }
  expect(actionIcon("open")).toBeUndefined();
});

test("a provider's endpoint is checked again in place; its rejected key opens its page", () => {
  const unreachable = item({
    kind: "provider",
    uid: "cn-1",
    reason_code: "provider_unreachable",
    action: { verb: "check", method: "POST", path: "/api/v1/providers/cn-1/check", body: null },
  });
  expect(inPlaceVerb(unreachable)).toBe("check");
  const rejected = item({
    kind: "provider",
    uid: "cn-1",
    reason_code: "provider_key_rejected",
    action: { verb: "replace_key", method: "GET", path: "/api/v1/providers/cn-1", body: null },
  });
  expect(inPlaceVerb(rejected)).toBeNull();
  expect(actionPage(rejected)).toBe("/model-providers/cn-1");
});
