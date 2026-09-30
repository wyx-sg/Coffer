// src/components/credentials/secretRows.test.ts — the Secrets page's row helpers: names, references, citers, groups.
import { describe, expect, test } from "vitest";

import type { CredentialRef } from "@/lib/api/credentials";
import { changeCount, planOf, shortPath } from "./scanPlan";
import {
  citersFromRefusal,
  citersOf,
  displayName,
  groupRows,
  isMissingHere,
  isValidSecretName,
  referenceOf,
  refsWaiting,
} from "./secretRows";
import { lastUsedLabel } from "./secretTimes";

function ref(over: Partial<CredentialRef> & { ref: string }): CredentialRef {
  return {
    bindings: [],
    cited_by: [],
    mentioned_by_skills: [],
    present: true,
    locked: false,
    created_at: null,
    last_used_at: null,
    readable_by_local_processes: false,
    unreferenced: false,
    uri: null,
    ...over,
  };
}

describe("secretRows", () => {
  test("a standalone secret shows its name and is referred to by its URI", () => {
    const row = ref({ ref: "secret/npm-token", uri: "coffer://secret/npm-token" });
    expect(displayName(row)).toBe("npm-token");
    expect(referenceOf(row)).toBe("coffer://secret/npm-token");
    const own = ref({ ref: "mcp_server/u1/TOKEN" });
    expect(displayName(own)).toBe("mcp_server/u1/TOKEN");
    expect(referenceOf(own)).toBe("mcp_server/u1/TOKEN");
  });

  test("names follow the spec's one-segment rule", () => {
    expect(isValidSecretName("aws.access_key-1")).toBe(true);
    expect(isValidSecretName("a/b")).toBe(false);
    expect(isValidSecretName("..")).toBe(false);
    expect(isValidSecretName("x".repeat(65))).toBe(false);
  });

  test("citers are the citing resources, then skills citing the URI not already named", () => {
    const row = ref({
      ref: "secret/gh",
      cited_by: [
        { kind: "mcp_server", name: "github", uid: "u1" },
        { kind: "skill", name: "notes", uid: "s1" },
      ],
      mentioned_by_skills: ["notes", "deploy"],
    });
    expect(citersOf(row).map((c) => [c.name, c.href])).toEqual([
      ["github", "/mcp-servers/github"],
      ["notes", "/skills/notes"],
      ["deploy", "/skills/deploy"],
    ]);
  });

  test("a refusal's resources become citers; anything malformed is dropped", () => {
    expect(
      citersFromRefusal({ resources: [{ kind: "channel", name: "SeaTalk", uid: "c1" }, { x: 1 }] }),
    ).toEqual([{ key: "channel:c1", kind: "channel", name: "SeaTalk", href: "/channels/c1" }]);
    expect(citersFromRefusal(null)).toEqual([]);
  });

  test("groups split used from unused and filter by name", () => {
    const rows = [ref({ ref: "secret/a-key" }), ref({ ref: "secret/b-key", unreferenced: true })];
    expect(groupRows(rows, "").inUse).toHaveLength(1);
    expect(groupRows(rows, "").unused).toHaveLength(1);
    expect(groupRows(rows, "B-K").inUse).toHaveLength(0);
    expect(groupRows(rows, "B-K").unused).toHaveLength(1);
  });

  test("a dry run's plan counts each secret and each file once", () => {
    const plan = planOf({
      dry_run: true,
      moved: [
        { id: "1", name: "aws-a", path: "/Users/me/.coffer/secrets/aws.env", uri: "" },
        { id: "2", name: "aws-b", path: "/Users/me/.coffer/secrets/aws.env", uri: "" },
      ],
      skipped: [],
    });
    expect(plan).toEqual({
      secrets: ["aws-a", "aws-b"],
      files: ["/Users/me/.coffer/secrets/aws.env"],
    });
    expect(changeCount(plan)).toBe(3);
    expect(shortPath("/Users/me/.coffer/secrets/aws.env")).toBe("~/.coffer/secrets/aws.env");
  });

  test("a ref is missing on this Mac when it is not stored, or stored under another key", () => {
    expect(isMissingHere(ref({ ref: "a" }))).toBe(false);
    expect(isMissingHere(ref({ ref: "a", present: false }))).toBe(true);
    expect(isMissingHere(ref({ ref: "a", locked: true }))).toBe(true);
  });

  test("only a new value or a new secret marks a ref as waiting", () => {
    const base = {
      status: "pending" as const,
      description: "",
      created_at: "",
      requested_by: "ui",
      decided_at: null,
      decided_by: null,
      destination_kind: null,
      destination_label: null,
      destination_uid: null,
      ref: null,
      slot: null,
      target: null,
    };
    const waiting = refsWaiting([
      { ...base, id: "1", op: "replace_value", ref: "secret/a" },
      { ...base, id: "2", op: "add_secret", ref: "secret/b" },
      { ...base, id: "3", op: "bind", ref: "secret/c" },
      { ...base, id: "4", op: "disable_protection" },
    ]);
    expect([...waiting].sort()).toEqual(["secret/a", "secret/b"]);
  });

  test("last used reads the way a person says it", () => {
    const t = ((key: string, vars?: Record<string, unknown>) =>
      `${key}${vars ? JSON.stringify(vars) : ""}`) as never;
    const now = new Date(2026, 8, 30, 15, 0, 0);
    const at = (d: Date) => d.toISOString();
    expect(lastUsedLabel(null, now, t, "en")).toBe("secrets.time.never");
    expect(lastUsedLabel(at(new Date(2026, 8, 30, 14, 58)), now, t, "en")).toContain("minutesAgo");
    expect(lastUsedLabel(at(new Date(2026, 8, 30, 9, 5)), now, t, "en")).toContain("09:05");
    expect(lastUsedLabel(at(new Date(2026, 8, 29, 9, 5)), now, t, "en")).toBe(
      "secrets.time.yesterday",
    );
    expect(lastUsedLabel(at(new Date(2026, 6, 3, 9, 5)), now, t, "en")).toBe("Jul 3");
  });
});
