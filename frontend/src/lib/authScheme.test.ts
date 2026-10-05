// src/lib/authScheme.test.ts — splitting a pasted `Bearer <key>`, stripping a doubled scheme, and
// the scheme a secret row sends.
import { describe, expect, test } from "vitest";

import {
  defaultSchemeFor,
  schemeOfRow,
  splitScheme,
  storePlainRow,
  stripScheme,
  withScheme,
} from "@/lib/authScheme";
import type { KeyValueSecretRow } from "@/lib/secretValue";

const secret = (
  key: string,
  value = "abc",
  scheme?: "Bearer" | "Token" | null,
): KeyValueSecretRow => ({
  key,
  scheme,
  value: { kind: "new", name: "0".repeat(32), label: key, value },
});

describe("splitScheme", () => {
  test("splits a leading Bearer or Token, in any case", () => {
    expect(splitScheme("Bearer abc")).toEqual({ scheme: "Bearer", rest: "abc" });
    expect(splitScheme("bearer   abc")).toEqual({ scheme: "Bearer", rest: "abc" });
    expect(splitScheme("TOKEN abc def")).toEqual({ scheme: "Token", rest: "abc def" });
  });
  test("leaves a bare key, a bare scheme and a longer word alone", () => {
    expect(splitScheme("abc")).toBeNull();
    expect(splitScheme("Bearer")).toBeNull();
    expect(splitScheme("Bearer ")).toBeNull();
    expect(splitScheme("Bearerabc")).toBeNull();
  });
});

describe("stripScheme", () => {
  test("drops the scheme the row already names", () => {
    expect(stripScheme("Bearer abc", "Bearer")).toBe("abc");
    expect(stripScheme("bearer abc", "Bearer")).toBe("abc");
  });
  test("keeps a different scheme, and everything when there is none", () => {
    expect(stripScheme("Token abc", "Bearer")).toBe("Token abc");
    expect(stripScheme("Bearer abc", null)).toBe("Bearer abc");
    expect(stripScheme("Bearer abc", undefined)).toBe("Bearer abc");
  });
});

describe("row schemes", () => {
  test("Authorization defaults to Bearer, other keys to none", () => {
    expect(defaultSchemeFor("authorization")).toBe("Bearer");
    expect(defaultSchemeFor(" Authorization ")).toBe("Bearer");
    expect(defaultSchemeFor("X-Api-Key")).toBeNull();
  });
  test("a secret row sends its own choice, else the key's default; a plain row none", () => {
    expect(schemeOfRow(secret("Authorization"))).toBe("Bearer");
    expect(schemeOfRow(secret("Authorization", "abc", null))).toBeNull();
    expect(schemeOfRow(secret("X-Api-Key", "abc", "Token"))).toBe("Token");
    expect(schemeOfRow({ key: "Authorization", value: { kind: "plain", value: "x" } })).toBeNull();
  });
  test("choosing a scheme strips it off a new secret's typed value", () => {
    const row = withScheme(secret("Authorization", "Bearer abc"), "Bearer");
    expect(row.value.kind === "new" && row.value.value).toBe("abc");
  });
  test("storing a plain row splits a typed scheme, else strips the row's own", () => {
    const plain = (key: string, value: string): KeyValueSecretRow => ({
      key,
      value: { kind: "plain", value },
    });
    const split = storePlainRow(plain("X-Api-Key", "Token abc"), "label");
    expect(split.scheme).toBe("Token");
    expect(split.value.kind === "new" && split.value.value).toBe("abc");
    const bare = storePlainRow(plain("Authorization", "abc"), "label");
    expect(bare.scheme).toBe("Bearer");
    expect(bare.value.kind === "new" && bare.value.value).toBe("abc");
    const env = storePlainRow(plain("API_KEY", "Bearer abc"), "label", false);
    expect(env.scheme).toBeUndefined();
    expect(env.value.kind === "new" && env.value.value).toBe("Bearer abc");
  });
});
