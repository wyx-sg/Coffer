// frontend/src/lib/activity/activityText.test.ts
import { describe, expect, test } from "vitest";
import i18next from "@/i18n";
import backendKeys from "@/i18n/backend-keys.fixture.json";
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

  test("a secret Coffer hands to a server names the secret, the server and the variable", () => {
    const coffer = (details: Record<string, unknown>) =>
      describeActivity(t, makeEntry({ event_type: "secret_resolved", actor: "coffer", details }));
    expect(
      coffer({
        ref: "secret/GITHUB_TOKEN",
        destination_kind: "mcp_server",
        destination_uid: "u-1",
        destination_name: "github",
        slot: "GITHUB_TOKEN",
      }),
    ).toBe("Handed secret “GITHUB_TOKEN” to MCP server github (environment variable GITHUB_TOKEN)");
    expect(
      coffer({
        ref: "secret/SENTRY",
        destination_kind: "mcp_server",
        destination_name: "sentry",
        slot: "Authorization",
      }),
    ).toBe("Handed secret “SENTRY” to MCP server sentry (header Authorization)");
    expect(
      coffer({
        ref: "secret/JIRA",
        destination_kind: "mcp_server",
        destination_name: "jira · prod",
        slot: "prod:X-Api-Key",
      }),
    ).toBe("Handed secret “JIRA” to custom tool jira · prod (header X-Api-Key)");
    expect(
      coffer({
        ref: "secret/OPENAI",
        destination_kind: "provider",
        destination_name: "openai",
        slot: "key",
      }),
    ).toBe("Handed secret “OPENAI” to model connection openai (API key)");
    // Never claims a coffer run happened when Coffer handed the value to a server.
    expect(
      coffer({ ref: "secret/X", destination_kind: "mcp_server", destination_name: "s", slot: "X" }),
    ).not.toContain("coffer run");
    const zh = i18next.getFixedT("zh") as TFunction;
    expect(
      describeActivity(
        zh,
        makeEntry({
          event_type: "secret_resolved",
          details: {
            ref: "secret/GITHUB_TOKEN",
            destination_kind: "mcp_server",
            destination_name: "github",
            slot: "GITHUB_TOKEN",
          },
        }),
      ),
    ).toBe("把密钥“GITHUB_TOKEN”交给了 MCP 服务器 github（环境变量 GITHUB_TOKEN）");
  });

  test("a secret coffer run hands to a program names the program and its folder", () => {
    const run = (details: Record<string, unknown>) =>
      describeActivity(t, makeEntry({ event_type: "secret_resolved", actor: "cli", details }));
    expect(
      run({ ref: "secret/OPENAI_KEY", name: "OPENAI_KEY", argv0: "python", cwd: "~/proj" }),
    ).toBe("Handed secret “OPENAI_KEY” to coffer run: python, in ~/proj");
    expect(
      run({
        ref: "secret/OPENAI_KEY",
        name: "OPENAI_KEY",
        argv0: "/usr/bin/python3",
        cwd: "/Users/ann/proj",
      }),
    ).toBe("Handed secret “OPENAI_KEY” to coffer run: python3, in ~/proj");
    expect(run({ ref: "secret/OPENAI_KEY", argv0: "python" })).toBe(
      "Handed secret “OPENAI_KEY” to coffer run: python",
    );
    const zh = i18next.getFixedT("zh") as TFunction;
    expect(
      describeActivity(
        zh,
        makeEntry({
          event_type: "secret_resolved",
          details: { ref: "secret/OPENAI_KEY", name: "OPENAI_KEY", argv0: "python", cwd: "~/proj" },
        }),
      ),
    ).toBe("把密钥“OPENAI_KEY”交给了 coffer run：python，在 ~/proj");
  });

  test("secret_set names the secret, and says when it replaced a value", () => {
    const set = (details: Record<string, unknown>) =>
      describeActivity(t, makeEntry({ event_type: "secret_set", details }));
    expect(set({ ref: "secret/SENTRY_TOKEN", replaced: true })).toBe(
      "Stored secret “SENTRY_TOKEN”, replacing its value",
    );
    expect(set({ ref: "secret/SENTRY_TOKEN", replaced: false })).toBe(
      "Stored secret “SENTRY_TOKEN”",
    );
    // A ref outside `secret/` is named by its last segment.
    expect(set({ ref: "mcp_server/github/GH_TOKEN" })).toBe("Stored secret “GH_TOKEN”");
  });

  test("a minted secret reads by its name, never by its id", () => {
    const id = "fe55638667a74ca18a73e78cf67f5fe5";
    const row = (details: Record<string, unknown>) =>
      makeEntry({ event_type: "secret_resolved", actor: "coffer", details });
    const sync = {
      ref: `secret/${id}`,
      destination_kind: "sync_remote",
      destination_name: "sync",
      slot: "token",
    };
    // Today's name wins, so a renamed secret reads by its new name.
    const live = new Map([[`secret/${id}`, "Git token"]]);
    expect(describeActivity(t, row({ ...sync, ref_label: "Old name" }), live)).toBe(
      "Handed secret “Git token” to the sync remote (access token)",
    );
    // A deleted secret reads by the name the row recorded.
    expect(describeActivity(t, row({ ...sync, ref_label: "Old name" }), new Map())).toBe(
      "Handed secret “Old name” to the sync remote (access token)",
    );
    // Nobody named it: an unnamed secret, not its id.
    expect(describeActivity(t, row(sync), new Map([[`secret/${id}`, null]]))).toBe(
      "Handed an unnamed secret to the sync remote (access token)",
    );
    expect(describeActivity(t, row(sync))).not.toContain(id);
  });

  test("sync_run reads the round's outcome and file counts", () => {
    const round = (details: Record<string, unknown>) =>
      describeActivity(t, makeEntry({ event_type: "sync_run", actor: "sync", details }));
    expect(round({ status: "pulled_and_pushed", pulled: 3, pushed: 1 })).toBe(
      "Synced: pulled 3 files, pushed 1",
    );
    expect(round({ status: "pulled", pulled: 1, pushed: 0 })).toBe("Synced: pulled 1 file");
    expect(round({ status: "nothing_to_do", pulled: 0, pushed: 0 })).toBe(
      "Synced: nothing to pull or push",
    );
    expect(round({ status: "held", held: 12 })).toBe("Sync held: it would delete 12 files");
    expect(round({ status: "stopped", conflicts: 2 })).toBe("Sync stopped: 2 files in conflict");
  });

  test("a change names its file, setting or approval", () => {
    expect(
      describeActivity(
        t,
        makeEntry({
          event_type: "vault_file_edited",
          details: { path: "knowledge/notes/x.md", version: "abc" },
        }),
      ),
    ).toBe("Edited vault file knowledge/notes/x.md on disk");
    expect(
      describeActivity(
        t,
        makeEntry({
          event_type: "retention_updated",
          details: { table: "mcp_invocations", previous_days: 30, retention_days: 90 },
        }),
      ),
    ).toBe("Changed how long “Tool calls” is kept: 30 days → 90 days");
    expect(
      describeActivity(
        t,
        makeEntry({
          event_type: "retention_updated",
          details: { table: "audit_log", previous_days: 30, retention_days: null },
        }),
      ),
    ).toBe("Changed how long “Changes” is kept: 30 days → forever");
    expect(
      describeActivity(
        t,
        makeEntry({
          event_type: "secret_approval_requested",
          details: { approval_id: "a", op: "bind", ref: "secret/STRIPE" },
        }),
      ),
    ).toBe("Asked for approval to send secret “STRIPE” somewhere new");
    expect(
      describeActivity(
        t,
        makeEntry({
          event_type: "secret_approval_approved",
          details: { op: "disable_protection" },
        }),
      ),
    ).toBe("Approved turning off secret approval");
  });

  test("a row missing a field reads the sentence without it, never a blank", () => {
    // An old secret_resolved row with no ref and no destination.
    expect(describeActivity(t, makeEntry({ event_type: "secret_resolved", details: {} }))).toBe(
      "Handed a secret over for use",
    );
    // A hand-off whose destination has no name drops it rather than leaving "to MCP server ".
    expect(
      describeActivity(
        t,
        makeEntry({
          event_type: "secret_resolved",
          details: { ref: "secret/A", destination_kind: "mcp_server", slot: "A" },
        }),
      ),
    ).toBe("Handed secret “A” over for use");
    expect(describeActivity(t, makeEntry({ event_type: "secret_set" }))).toBe("Stored a secret");
    expect(
      describeActivity(t, makeEntry({ event_type: "sync_plaintext_pushed", details: {} })),
    ).toBe("Pushed files a round had refused as a plaintext secret");
    expect(
      describeActivity(
        t,
        makeEntry({ event_type: "capability_enabled", resource_name: "fs", details: {} }),
      ),
    ).toBe("Turned on a capability on fs");
  });

  test("no event, with or without details, renders an empty placeholder", () => {
    const events: string[] = backendKeys.auditEvents;
    const odd = {
      ref: 7,
      path: null,
      destination_kind: "mcp_server",
      status: "pulled",
      agents: [],
    };
    for (const lang of ["en", "zh"]) {
      const tl = i18next.getFixedT(lang) as TFunction;
      for (const event_type of events) {
        for (const details of [null, {}, odd]) {
          const line = describeActivity(tl, makeEntry({ event_type, resource_name: "r", details }));
          expect(line, `${lang}:${event_type}`).not.toMatch(/undefined|null|\{\{|\(\)|（）/);
          expect(line, `${lang}:${event_type}`).not.toMatch(/ {2}| $/);
        }
      }
    }
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
        handoff: null,
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
        handoff: null,
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
      handoff: null,
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
        handoff: null,
        record: { logger: "coffer.sync" },
      }),
    ).toBe("coffer.sync");
    expect(
      daemonLogger({
        timestamp: null,
        level: null,
        event: null,
        offset: 0,
        handoff: null,
        record: { raw: "boom" },
      }),
    ).toBe("");
  });
});
