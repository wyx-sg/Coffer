// src/lib/secretValue.test.ts — how a stored ref is shown and cited.
import { describe, expect, test } from "vitest";

import { secretReferenceOf } from "./secretValue";

describe("secretReferenceOf", () => {
  test("a standalone secret is cited by its coffer:// URI", () => {
    expect(secretReferenceOf("secret/openai-key")).toBe("coffer://secret/openai-key");
  });

  test("any other ref is shown as itself", () => {
    expect(secretReferenceOf("provider/3f2a9c/key")).toBe("provider/3f2a9c/key");
  });
});
