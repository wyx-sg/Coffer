// src/lib/mcp/serverRows.test.ts — an HTTP server's auth schemes between its rows and its config.
import { describe, expect, test } from "vitest";

import type { KeyValueSecretRow } from "@/lib/secretValue";
import { authSchemesField, rowsFromParsed, rowsOf } from "./serverRows";

const stored = (key: string, scheme?: "Bearer" | "Token" | null): KeyValueSecretRow => ({
  key,
  scheme,
  value: { kind: "stored", name: `${key}-secret` },
});

describe("auth_schemes", () => {
  test("only secret rows with a scheme are written; Authorization defaults to Bearer", () => {
    const rows: KeyValueSecretRow[] = [
      stored("Authorization"),
      stored("X-Api-Key", "Token"),
      stored("X-Other", null),
      { key: "X-Team", scheme: "Bearer", value: { kind: "plain", value: "core" } },
    ];
    expect(authSchemesField(rows)).toEqual({
      auth_schemes: { Authorization: "Bearer", "X-Api-Key": "Token" },
    });
    expect(authSchemesField([stored("X-Other", null)])).toEqual({});
  });

  test("a stored config loads back into the same rows; a header without a scheme is None", () => {
    const config = {
      transport: {
        type: "http",
        secret_refs: { Authorization: "secret/aaa", "X-Api-Key": "secret/bbb" },
        auth_schemes: { Authorization: "Bearer" },
      },
    };
    const rows = rowsOf(config, [{ key: "X-Team", value: "core" }]);
    expect(rows.map((r) => [r.key, r.scheme])).toEqual([
      ["Authorization", "Bearer"],
      ["X-Api-Key", null],
      ["X-Team", undefined],
    ]);
    expect(authSchemesField(rows)).toEqual({ auth_schemes: { Authorization: "Bearer" } });
  });

  test("a pasted header's scheme becomes its row's; a bare secret is sent as is", () => {
    const rows = rowsFromParsed([
      { key: "Authorization", value: "abc", isSecret: true, scheme: "Bearer" },
      { key: "X-Api-Key", value: "def", isSecret: true },
    ]);
    expect(authSchemesField(rows)).toEqual({ auth_schemes: { Authorization: "Bearer" } });
  });

  test("a header waiting for its token keeps its scheme until it is promoted", () => {
    const [row] = rowsFromParsed(
      [{ key: "Authorization", value: "", isSecret: true, scheme: "Bearer" }],
      true,
    );
    expect(row.value.kind).toBe("plain");
    expect(row.scheme).toBe("Bearer");
  });
});
