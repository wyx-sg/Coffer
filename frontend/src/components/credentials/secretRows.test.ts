// src/components/credentials/secretRows.test.ts — the Secrets page's row helpers: names, references, citers, groups.
import { describe, expect, test } from "vitest";

import type { CredentialRef } from "@/lib/api/credentials";
import { changeCount, planOf, shortPath } from "./scanPlan";
import {
  citersFromRefusal,
  citersOf,
  displayName,
  groupRows,
  isValidSecretName,
  referenceOf,
} from "./secretRows";

function ref(over: Partial<CredentialRef> & { ref: string }): CredentialRef {
  return {
    bindings: [],
    cited_by: [],
    mentioned_by_skills: [],
    present: true,
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
});
