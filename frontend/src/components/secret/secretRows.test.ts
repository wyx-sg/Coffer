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
    label: null,
    description: null,
    created_for: null,
    ...over,
  };
}

describe("secretRows", () => {
  const HEX = "0123456789abcdef0123456789abcdef";

  test("a secret is referred to by its URI", () => {
    const row = ref({ ref: `secret/${HEX}`, uri: `coffer://secret/${HEX}` });
    expect(referenceOf(row)).toBe(`coffer://secret/${HEX}`);
    expect(referenceOf(ref({ ref: `secret/${HEX}` }))).toBe(`secret/${HEX}`);
  });

  test("the display name is the label, else a readable default, never a hex id", () => {
    // A label wins.
    expect(displayName(ref({ ref: `secret/${HEX}`, label: "GitHub token" }))).toBe("GitHub token");
    // Unlabelled: the first citer and the slot it cites it in (read from the binding).
    const cited = ref({
      ref: `secret/${HEX}`,
      cited_by: [{ kind: "mcp_server", name: "server", uid: "u1", slot: null }],
      bindings: [
        {
          approval_id: null,
          destination_kind: "mcp_server",
          destination_uid: "u1",
          slot: "API_KEY",
          status: "approved",
        },
      ],
    });
    expect(displayName(cited)).toBe("server · API_KEY");
    // No slot known: the citer alone; nothing known: the placeholder.
    expect(displayName({ ...cited, bindings: [] })).toBe("server");
    expect(displayName(ref({ ref: `secret/${HEX}` }), "Unnamed")).toBe("Unnamed");
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
        { kind: "mcp_server", name: "github", uid: "u1", slot: null },
        { kind: "skill", name: "notes", uid: "s1", slot: null },
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
      citersFromRefusal({
        resources: [{ kind: "channel", name: "SeaTalk", uid: "c1", slot: null }, { x: 1 }],
      }),
    ).toEqual([
      { key: "channel:c1", kind: "channel", uid: "c1", name: "SeaTalk", href: "/channels/c1" },
    ]);
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
