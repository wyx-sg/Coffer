// src/components/secret/secretRows.test.ts — the Secrets page's row helpers: names, references, citers, groups.
import { describe, expect, test } from "vitest";

import type { SecretRef } from "@/lib/api/secret";
import {
  citersFromRefusal,
  citersOf,
  displayName,
  isMissingHere,
  isValidSecretName,
  referenceOf,
} from "./secretRows";
import { shortDate } from "./secretTimes";

function ref(over: Partial<SecretRef> & { ref: string }): SecretRef {
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

  test("a ref is missing on this Mac when it is not stored, or stored under another key", () => {
    expect(isMissingHere(ref({ ref: "a" }))).toBe(false);
    expect(isMissingHere(ref({ ref: "a", present: false }))).toBe(true);
    expect(isMissingHere(ref({ ref: "a", locked: true }))).toBe(true);
  });

  test("a created day is the US short date, with the year once it is a past year", () => {
    const now = new Date(2026, 8, 30, 15, 0, 0);
    expect(shortDate(new Date(2026, 7, 12, 9).toISOString(), "en", now)).toBe("Aug 12");
    expect(shortDate(new Date(2025, 6, 3, 9).toISOString(), "en", now)).toBe("Jul 3, 2025");
    expect(shortDate("not a date", "en", now)).toBe("not a date");
  });
});
